import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.models.rag import (
    Paper2EvalRequest,
    Paper2EvalResponse,
    TopicNoteSummaryRequest,
    TopicNoteSummaryResponse,
)
from app.db.supabase_client import get_supabase_client
from app.services.llm_client import generate_with_fallback

logger = logging.getLogger("pathwise")

# ---------------------------------------------------------------------------
# Schema (confirmed from information_schema)
# ---------------------------------------------------------------------------
CANONICAL_TOPICS_TABLE = "canonical_topics"   # id, subject, topic_name, description
PAPER2_QUESTIONS_TABLE = "paper2_questions"   # id, subject, sub_question, topic_id, question_text, model_answer, marks
AI_CACHE_TABLE = "ai_content_cache"           # cache_key, content_type, payload, provider, created_at


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_json_response(raw: str) -> Dict[str, Any]:
    """Extracts the first JSON object from a model response, tolerating code fences or extra text."""
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in AI response.")
    return json.loads(text[start:end + 1])


def _compute_waec_grade(percentage: float) -> str:
    """Computes WAEC grade (A1 to F9) from a percentage."""
    if percentage >= 75.0:
        return "A1"
    elif percentage >= 70.0:
        return "B2"
    elif percentage >= 65.0:
        return "B3"
    elif percentage >= 60.0:
        return "C4"
    elif percentage >= 55.0:
        return "C5"
    elif percentage >= 50.0:
        return "C6"
    elif percentage >= 45.0:
        return "D7"
    elif percentage >= 40.0:
        return "E8"
    else:
        return "F9"


def _resolve_topic(supabase, identifier: str, subject: str) -> Tuple[Optional[str], str, str]:
    """
    Finds a canonical topic by id or topic_name (case-insensitive).
    Returns (topic_id, topic_name, description). topic_id is None if not found.
    """
    rows = supabase.table(CANONICAL_TOPICS_TABLE).select("*").execute().data or []
    wanted = identifier.strip().lower()

    matches = [
        r for r in rows
        if str(r.get("id") or "").strip().lower() == wanted
        or str(r.get("topic_name") or "").strip().lower() == wanted
    ]
    if not matches:
        return None, identifier, ""

    subj = subject.strip().lower()
    preferred = [r for r in matches if str(r.get("subject") or "").strip().lower() == subj]
    chosen = (preferred or matches)[0]

    return (
        chosen.get("id"),
        chosen.get("topic_name") or identifier,
        chosen.get("description") or "",
    )


# ---------------------------------------------------------------------------
# AI result cache (only AI-generated results are ever stored)
# ---------------------------------------------------------------------------
def _model_to_dict(model) -> Dict[str, Any]:
    """Works with both Pydantic v1 and v2 models."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _normalize_text(value: str) -> str:
    """Collapses whitespace and trims. Case is preserved, since case can matter in maths answers."""
    return " ".join((value or "").split())


def _notes_cache_key(subject: str, topic_code: str) -> str:
    return f"notes:{_normalize_text(subject).lower()}:{_normalize_text(topic_code).lower()}"


def _eval_cache_key(sub_question_id: str, student_answer: str) -> str:
    answer_hash = hashlib.sha256(_normalize_text(student_answer).encode("utf-8")).hexdigest()
    return f"eval:{sub_question_id}:{answer_hash}"


def _cache_get(supabase, cache_key: str) -> Optional[Dict[str, Any]]:
    """Returns the cached payload, or None on a miss or any cache error."""
    try:
        resp = (
            supabase.table(AI_CACHE_TABLE)
            .select("payload")
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0].get("payload")
    except Exception as e:
        logger.warning(f"AI cache read failed for key {cache_key}: {e}")
    return None


def _cache_set(
    supabase,
    cache_key: str,
    content_type: str,
    payload: Dict[str, Any],
    provider: Optional[str],
) -> None:
    """Stores an AI-generated payload. Errors are logged and never break the request."""
    try:
        supabase.table(AI_CACHE_TABLE).upsert(
            {
                "cache_key": cache_key,
                "content_type": content_type,
                "payload": payload,
                "provider": provider,
            },
            on_conflict="cache_key",
        ).execute()
    except Exception as e:
        logger.warning(f"AI cache write failed for key {cache_key}: {e}")


# ---------------------------------------------------------------------------
# Paper 2 evaluation
# ---------------------------------------------------------------------------
def evaluate_paper2_answer(request: Paper2EvalRequest) -> Paper2EvalResponse:
    """Evaluates a student's written response against the official WAEC marking reference."""
    supabase = get_supabase_client()

    cache_key = _eval_cache_key(request.sub_question_id, request.student_answer)
    cached = _cache_get(supabase, cache_key)
    if cached:
        try:
            logger.info("AI cache hit: paper2 evaluation")
            return Paper2EvalResponse(**cached)
        except Exception as e:
            logger.warning(f"Cached paper2 evaluation was unreadable, re-evaluating: {e}")

    try:
        q_resp = (
            supabase.table(PAPER2_QUESTIONS_TABLE)
            .select("*")
            .eq("id", request.sub_question_id)
            .execute()
        )
        if not q_resp.data:
            raise ValueError(f"Question ID {request.sub_question_id} not found.")

        q = q_resp.data[0]
        question_text = q.get("question_text") or ""
        model_answer = q.get("model_answer") or ""
        max_marks = float(q.get("marks") or 10.0)
        sub_label = q.get("sub_question") or ""
        subject = q.get("subject") or "Core Mathematics"

        topic_name = "General Practice"
        if q.get("topic_id"):
            t_resp = (
                supabase.table(CANONICAL_TOPICS_TABLE)
                .select("*")
                .eq("id", q["topic_id"])
                .execute()
            )
            if t_resp.data:
                topic_name = t_resp.data[0].get("topic_name") or topic_name

    except Exception as e:
        logger.error(f"Error fetching paper2 question data: {e}")
        return Paper2EvalResponse(
            sub_question_id=request.sub_question_id,
            earned_marks=0.0,
            max_marks=10.0,
            percentage=0.0,
            waec_grade="F9",
            feedback=f"Could not load question data: {str(e)}",
            step_breakdown=["0/10 marks: Error retrieving marking reference."],
            key_concepts_missed=["System database lookup error."],
            is_ai_evaluated=False,
        )

    prompt = f"""
You are an expert WASSCE Senior High School Chief Examiner in West Africa for {subject}.
Evaluate the student's written response strictly against the WAEC marking reference below.

Topic: {topic_name}
Question part: {sub_label}
Question: {question_text}
Maximum marks: {max_marks}

OFFICIAL MARKING REFERENCE / MODEL ANSWER:
{model_answer}

STUDENT'S WRITTEN ANSWER:
{request.student_answer}

Return valid JSON ONLY, with no markdown or code fences:
{{
  "earned_marks": a number between 0.0 and {max_marks},
  "feedback": "Detailed, encouraging breakdown based on WAEC criteria",
  "step_breakdown": ["Step 1 mark breakdown", "Step 2 mark breakdown"],
  "key_concepts_missed": ["Concept 1", "Concept 2"]
}}
"""
    ai_raw, provider = generate_with_fallback(prompt)
    if ai_raw:
        try:
            parsed = _parse_json_response(ai_raw)
            earned = max(0.0, min(float(parsed.get("earned_marks", 0.0)), max_marks))
            pct = (earned / max_marks) * 100.0 if max_marks > 0 else 0.0
            result = Paper2EvalResponse(
                sub_question_id=request.sub_question_id,
                earned_marks=earned,
                max_marks=max_marks,
                percentage=round(pct, 1),
                waec_grade=_compute_waec_grade(pct),
                feedback=parsed.get("feedback", "Evaluation completed."),
                step_breakdown=parsed.get("step_breakdown", []),
                key_concepts_missed=parsed.get("key_concepts_missed", []),
                is_ai_evaluated=True,
            )
            _cache_set(supabase, cache_key, "paper2_eval", _model_to_dict(result), provider)
            return result
        except Exception as e:
            logger.warning(f"AI evaluation parse error from {provider}: {e}. Using rule-based fallback.")

    return _heuristic_paper2_evaluation(
        request.sub_question_id,
        request.student_answer,
        model_answer,
        max_marks,
    )


# ---------------------------------------------------------------------------
# Study notes
# ---------------------------------------------------------------------------
def summarize_topic_notes(request: TopicNoteSummaryRequest) -> TopicNoteSummaryResponse:
    """Generates structured revision notes for a topic, using AI providers or a fallback template."""
    supabase = get_supabase_client()

    cache_key = _notes_cache_key(request.subject, request.topic_code)
    cached = _cache_get(supabase, cache_key)
    if cached:
        try:
            logger.info("AI cache hit: topic notes")
            return TopicNoteSummaryResponse(**cached)
        except Exception as e:
            logger.warning(f"Cached topic notes were unreadable, regenerating: {e}")

    topic_id: Optional[str] = None
    topic_name = request.topic_code
    topic_description = ""
    try:
        topic_id, topic_name, topic_description = _resolve_topic(
            supabase, request.topic_code, request.subject
        )
    except Exception as e:
        logger.warning(f"Error resolving canonical topic: {e}")

    sample_texts: List[str] = []
    if topic_id:
        try:
            pq_resp = (
                supabase.table(PAPER2_QUESTIONS_TABLE)
                .select("question_text, model_answer")
                .eq("topic_id", topic_id)
                .limit(5)
                .execute()
            )
            for q in pq_resp.data or []:
                if q.get("question_text"):
                    sample_texts.append(q["question_text"])
                if q.get("model_answer"):
                    sample_texts.append(q["model_answer"])
        except Exception as e:
            logger.warning(f"Error fetching questions for notes: {e}")

    context_parts = []
    if topic_description:
        context_parts.append(f"Topic description: {topic_description}")
    context_parts.extend(sample_texts)
    context_str = "\n".join(context_parts)[:2500]

    prompt = f"""
You are an expert WASSCE Senior High School Chief Examiner and Master Tutor in Ghana specializing in {request.subject}.
Generate punchy, high-yield, and highly structured revision study notes for the topic: "{topic_name}".

Context from official WAEC past questions and model answers:
{context_str if context_str else "Standard WAEC High School Curriculum"}

CRITICAL FORMATTING RULE:
For every array item in key_definitions, essential_formulas, common_waec_traps, and step_by_step_exam_tips, use the exact format "Short Title: Concise body text". Keep titles under 5 words so the UI can render clean badges/cards.

Return valid JSON ONLY, with no markdown or code fences:
{{
  "topic_name": "{topic_name}",
  "subject": "{request.subject}",
  "summary_text": "A punchy 2-3 sentence overview explaining how this topic is tested in WASSCE Paper 1 & Paper 2 and the core rule to master.",
  "key_definitions": [
    "Term Name: Crisp, candidate-friendly definition as expected in WASSCE Paper 2.",
    "Law/Principle Name: Complete statement of the law with required conditions."
  ],
  "essential_formulas": [
    "Formula Name: x = [-b ± √(b² - 4ac)] / (2a) — Apply for standard quadratic forms where a ≠ 0.",
    "Rule Name: Expression or equation — Explanation of sign conventions and SI units."
  ],
  "common_waec_traps": [
    "Sign Reversal Trap: Forgetting to reverse inequality signs when multiplying or dividing by negative numbers.",
    "Unit Omission Error: Leaving final answers without required units or incorrect decimal rounding."
  ],
  "step_by_step_exam_tips": [
    "Step 1 Setup: Explicitly state given variables and initial formula before substitution to earn method marks.",
    "Step 2 Working: Show intermediate algebraic simplification steps clearly for partial credit."
  ]
}}
"""
    ai_raw, provider = generate_with_fallback(prompt)
    if ai_raw:
        try:
            parsed = _parse_json_response(ai_raw)
            result = TopicNoteSummaryResponse(
                topic_name=parsed.get("topic_name", topic_name),
                subject=request.subject,
                key_definitions=parsed.get("key_definitions", []),
                essential_formulas=parsed.get("essential_formulas", []),
                common_waec_traps=parsed.get("common_waec_traps", []),
                step_by_step_exam_tips=parsed.get("step_by_step_exam_tips", []),
                summary_text=parsed.get("summary_text", f"Summary notes for {topic_name}."),
                is_ai_generated=True,
            )
            _cache_set(supabase, cache_key, "topic_notes", _model_to_dict(result), provider)
            return result
        except Exception as e:
            logger.warning(f"AI notes parse error from {provider}: {e}. Using template notes.")

    return TopicNoteSummaryResponse(
        topic_name=topic_name,
        subject=request.subject,
        key_definitions=[
            f"Core Concept: Fundamental conceptual understanding of {topic_name} under the WASSCE syllabus.",
            f"Syllabus Definition: Standard definitions, quantities, and variables required in WASSCE Paper 2.",
        ],
        essential_formulas=[
            f"Standard Working Form: Key equations, fundamental principles, and step procedures for {topic_name}.",
        ],
        common_waec_traps=[
            "Intermediate Steps Trap: Failing to show full intermediate working steps in Paper 2 calculation questions.",
            "Units & Radian Mode: Omitting standard SI units or using incorrect calculator mode in final answers.",
            "Sign Conventions: Misapplying sign rules during algebraic transposition.",
        ],
        step_by_step_exam_tips=[
            "State Given Data: Write down the relevant formula and given parameters before numerical substitution.",
            "Sequential Working: Keep calculations clear and step-by-step so examiners can award partial method marks.",
            "Diagram Precision: Draw clear, well-labelled diagrams whenever requested by the question.",
        ],
        summary_text=(
            f"Revision notes summary for {topic_name} under {request.subject}. "
            "Review official WAEC past paper schemes to solidify method steps and accuracy marks."
        ),
        is_ai_generated=False,
    )


generate_summary_notes = summarize_topic_notes


def _heuristic_paper2_evaluation(
    sub_question_id: str,
    student_answer: str,
    model_answer: str,
    max_marks: float,
) -> Paper2EvalResponse:
    clean_ans = student_answer.strip()
    if not clean_ans:
        return Paper2EvalResponse(
            sub_question_id=sub_question_id,
            earned_marks=0.0,
            max_marks=max_marks,
            percentage=0.0,
            waec_grade="F9",
            feedback="No answer was provided.",
            step_breakdown=["0 marks: Blank response."],
            key_concepts_missed=["Complete question requirement."],
            is_ai_evaluated=False,
        )

    reference_words = set(model_answer.lower().split())
    student_words = set(clean_ans.lower().split())

    overlap = len(student_words & reference_words)
    ratio = min(1.0, overlap / max(1, len(reference_words) * 0.3))

    earned = round(ratio * max_marks * 0.8, 1) if len(clean_ans) > 10 else 1.0
    earned = min(earned, max_marks)
    pct = round((earned / max_marks) * 100.0, 1) if max_marks > 0 else 0.0

    return Paper2EvalResponse(
        sub_question_id=sub_question_id,
        earned_marks=earned,
        max_marks=max_marks,
        percentage=pct,
        waec_grade=_compute_waec_grade(pct),
        feedback=(
            "AI marking is temporarily unavailable, so this is an automated keyword estimate. "
            "Compare your working with the model answer."
        ),
        step_breakdown=[
            f"Estimated {earned}/{max_marks} marks based on keyword overlap with the model answer.",
            "Review the official WAEC model answer to check your method steps.",
        ],
        key_concepts_missed=["Ensure all intermediate working steps and final units are clearly shown."],
        is_ai_evaluated=False,
    )