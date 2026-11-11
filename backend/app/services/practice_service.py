import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple, Optional

import httpx
from fastapi import HTTPException

from app.db.supabase_client import supabase_admin
from app.models.diagnostic import AnswerSubmission, TopicBreakdown
from app.models.practice import (
    AutosaveAnswerRequest,
    AutosaveAnswerResponse,
    PracticeStartResponse,
    PracticeSubmitResponse,
    QuestionReviewItem,
)
from app.services.adaptive_engine import (
    _format_questions,
    _mark_seen,
    _save_attempt_answer,
    _topic_fields,
    get_tier_from_score,
    get_waec_grade,
    shuffle_options_for_question,
)
from app.services.study_path_service import get_study_path
from app.utils.logger import logger

MIN_PRACTICE_QUESTIONS = 20
VALID_OPTIONS = {"A", "B", "C", "D", "E"}
QUESTION_POOL_LIMIT = 1000


def _load_session(user_id: str, session_id: str) -> Dict[str, Any]:
    try:
        res = (
            supabase_admin.table("practice_sessions")
            .select("*")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
    except (httpx.RequestError, Exception) as err:
        logger.warning(f"Database connection glitch in _load_session: {err}")
        raise HTTPException(
            status_code=503,
            detail="Database connection temporarily unavailable. Answer saved locally.",
        )

    if not res.data:
        raise HTTPException(status_code=404, detail="Practice session not found")
    return res.data[0]


def _questions_by_id(q_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    try:
        res = (
            supabase_admin.table("questions")
            .select("*, canonical_topics(*)")
            .in_("id", q_ids)
            .execute()
        )
        return {str(q["id"]): q for q in (res.data or [])}
    except (httpx.RequestError, Exception) as err:
        logger.warning(f"Database connection glitch in _questions_by_id: {err}")
        raise HTTPException(
            status_code=503,
            detail="Database connection temporarily unavailable.",
        )


def _saved_rows(user_id: str, session_id: str) -> List[Dict[str, Any]]:
    try:
        res = (
            supabase_admin.table("attempt_answers")
            .select("question_id, selected_answer, is_correct")
            .eq("user_id", user_id)
            .eq("attempt_id", session_id)
            .execute()
        )
        return res.data or []
    except (httpx.RequestError, Exception) as err:
        logger.warning(f"Database connection glitch in _saved_rows: {err}")
        return []


def _saved_answers(user_id: str, session_id: str) -> List[AnswerSubmission]:
    return [
        AnswerSubmission(
            question_id=str(row["question_id"]),
            selected_option=str(row["selected_answer"]).upper(),
        )
        for row in _saved_rows(user_id, session_id)
        if row.get("selected_answer")
    ]


def _grade_choice(q: Dict[str, Any], q_map: Dict[str, str], selected_label: str) -> bool:
    original = q_map.get(selected_label, "E")
    if original == "E":
        return False
    return original == (q.get("correct_option") or "").upper()


def _topic_breakdown(
    q_ids: List[str],
    q_dict: Dict[str, Dict[str, Any]],
    correct_ids: Set[str],
) -> List[TopicBreakdown]:
    stats: Dict[str, Dict[str, Any]] = {}
    for q_id in q_ids:
        q = q_dict.get(q_id)
        if not q:
            continue
        code, name = _topic_fields(q)
        entry = stats.setdefault(code, {"name": name, "correct": 0, "total": 0})
        entry["total"] += 1
        if q_id in correct_ids:
            entry["correct"] += 1

    return [
        TopicBreakdown(
            topic_code=code,
            topic_name=data["name"],
            correct_count=data["correct"],
            total_count=data["total"],
            percentage=round((data["correct"] / data["total"]) * 100, 2) if data["total"] > 0 else 0.0,
        )
        for code, data in stats.items()
    ]


def _build_submit_response(
    session: Dict[str, Any],
    q_dict: Dict[str, Dict[str, Any]],
    chosen: Dict[str, str],
    score: float,
    completed_at: str,
) -> PracticeSubmitResponse:
    q_ids = [str(q) for q in (session["question_ids"] or [])]
    shuffled_map = session.get("shuffled_options") or {}

    correct_ids: Set[str] = set()
    question_reviews: List[QuestionReviewItem] = []

    for q_id in q_ids:
        q = q_dict.get(q_id)
        if not q:
            continue

        q_map = shuffled_map.get(q_id) or {}
        user_selected = chosen.get(q_id)

        orig_correct = (q.get("correct_option") or "").strip().upper()
        # Find which shuffled label ('A'-'D') corresponds to the original correct option
        correct_shuffled = next(
            (lbl for lbl, orig in q_map.items() if orig.upper() == orig_correct),
            orig_correct,
        )

        is_correct = (user_selected == correct_shuffled) if user_selected else False
        if is_correct:
            correct_ids.add(q_id)

        # Format question options using the session's shuffled map
        formatted_q_list = _format_questions([q_id], q_dict, {q_id: q_map})
        formatted_q = formatted_q_list[0] if formatted_q_list else None

        options = formatted_q.options if formatted_q else []
        question_text = formatted_q.question_text if formatted_q else (q.get("question_text") or "")
        diagram_url = formatted_q.diagram_url if formatted_q else q.get("diagram_url")
        _, topic_name = _topic_fields(q)

        explanation = (
            q.get("explanation")
            or q.get("solution")
            or f"The correct answer is Option {correct_shuffled}."
        )

        question_reviews.append(
            QuestionReviewItem(
                question_id=q_id,
                question_text=question_text,
                topic_name=topic_name,
                diagram_url=diagram_url,
                selected_option=user_selected,
                correct_option=correct_shuffled,
                is_correct=is_correct,
                explanation=explanation,
                options=options,
            )
        )

    return PracticeSubmitResponse(
        session_id=str(session["id"]),
        subject=session["subject"],
        score=score,
        target_tier=session["target_tier"],
        new_tier=get_tier_from_score(score),
        waec_grade=get_waec_grade(score),
        completed_at=completed_at,
        topic_breakdown=_topic_breakdown(q_ids, q_dict, correct_ids),
        question_reviews=question_reviews,
    )


def _stored_result(user_id: str, session: Dict[str, Any]) -> PracticeSubmitResponse:
    q_ids = [str(q) for q in (session["question_ids"] or [])]
    q_dict = _questions_by_id(q_ids)

    chosen: Dict[str, str] = {}
    for row in _saved_rows(user_id, str(session["id"])):
        if row.get("selected_answer"):
            chosen[str(row["question_id"])] = str(row["selected_answer"]).upper()

    return _build_submit_response(
        session,
        q_dict,
        chosen,
        float(session.get("score") or 0.0),
        session.get("completed_at") or "",
    )


def _resume_practice(user_id: str, session: Dict[str, Any]) -> PracticeStartResponse:
    q_ids = [str(q) for q in (session["question_ids"] or [])]
    q_dict = _questions_by_id(q_ids)
    questions = _format_questions(q_ids, q_dict, session["shuffled_options"] or {})
    session_id = str(session["id"])
    logger.info(f"Resuming practice session {session_id} for user {user_id}")

    return PracticeStartResponse(
        session_id=session_id,
        subject=session["subject"],
        target_tier=session["target_tier"],
        total_questions=len(questions),
        questions=questions,
        saved_answers=_saved_answers(user_id, session_id),
    )


def _require_subject_ready(user_id: str, subject: str) -> Dict[str, Any]:
    try:
        res = (
            supabase_admin.table("user_subjects")
            .select("current_tier, diagnostic_completed, archived")
            .eq("user_id", user_id)
            .eq("subject", subject)
            .execute()
        )
    except (httpx.RequestError, Exception) as err:
        logger.warning(f"Database connection glitch in _require_subject_ready: {err}")
        raise HTTPException(
            status_code=503,
            detail="Database connection temporarily unavailable.",
        )

    if not res.data:
        raise HTTPException(status_code=400, detail=f"Subject not enrolled: {subject}")

    row = res.data[0]
    if row.get("archived"):
        raise HTTPException(
            status_code=400,
            detail=f"{subject} is hidden from your dashboard. Add it back to start practice.",
        )
    if not row.get("diagnostic_completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Finish the {subject} diagnostic before you start practice.",
        )
    return row


def start_practice(
    user_id: str,
    subject: str,
    num_questions: int = MIN_PRACTICE_QUESTIONS,
) -> PracticeStartResponse:
    if num_questions < MIN_PRACTICE_QUESTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum practice session size is {MIN_PRACTICE_QUESTIONS} questions",
        )

    subject_row = _require_subject_ready(user_id, subject)
    current_tier = subject_row.get("current_tier") or "Beginner"

    try:
        open_res = (
            supabase_admin.table("practice_sessions")
            .select("*")
            .eq("user_id", user_id)
            .eq("subject", subject)
            .eq("status", "in_progress")
            .limit(1)
            .execute()
        )
        if open_res.data:
            return _resume_practice(user_id, open_res.data[0])

        # Get user's weak focus topics to prioritize in practice
        study_path_data = get_study_path(user_id, subject)
        focus_codes = {f["topic_code"] for f in study_path_data.get("focus_topics", [])}

        seen_res = (
            supabase_admin.table("seen_questions")
            .select("question_id")
            .eq("user_id", user_id)
            .eq("subject", subject)
            .execute()
        )
        seen_ids = {str(r["question_id"]) for r in (seen_res.data or [])}

        questions_res = (
            supabase_admin.table("questions")
            .select("*, canonical_topics(*)")
            .eq("subject", subject)
            .limit(QUESTION_POOL_LIMIT)
            .execute()
        )
    except (httpx.RequestError, Exception) as err:
        logger.warning(f"Database connection glitch in start_practice: {err}")
        raise HTTPException(
            status_code=503,
            detail="Database connection temporarily unavailable.",
        )

    rows = questions_res.data or []
    unseen = [q for q in rows if str(q["id"]) not in seen_ids]
    pool = unseen if len(unseen) >= num_questions else rows

    # Separate pool into weak topic questions vs other questions
    focus_pool = []
    other_pool = []
    for q in pool:
        code, _ = _topic_fields(q)
        if code in focus_codes:
            focus_pool.append(q)
        else:
            other_pool.append(q)

    random.shuffle(focus_pool)
    random.shuffle(other_pool)

    # Pick ~70% of practice questions from weak focus topics if available
    target_focus = int(num_questions * 0.7)
    selected_focus = focus_pool[:target_focus]
    needed_other = num_questions - len(selected_focus)
    selected_other = other_pool[:needed_other]

    selected_raw = selected_focus + selected_other
    if len(selected_raw) < num_questions and len(focus_pool) > len(selected_focus):
        remaining = num_questions - len(selected_raw)
        selected_raw += focus_pool[len(selected_focus) : len(selected_focus) + remaining]

    random.shuffle(selected_raw)

    if len(selected_raw) < MIN_PRACTICE_QUESTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough {subject} questions are available for practice yet.",
        )

    question_ids: List[str] = []
    shuffled_options_master: Dict[str, Any] = {}
    for q in selected_raw:
        q_id = str(q["id"])
        question_ids.append(q_id)
        _, mapping = shuffle_options_for_question(q)
        shuffled_options_master[q_id] = mapping

    q_dict = {str(q["id"]): q for q in selected_raw}
    formatted = _format_questions(question_ids, q_dict, shuffled_options_master)

    try:
        session_res = (
            supabase_admin.table("practice_sessions")
            .insert(
                {
                    "user_id": user_id,
                    "subject": subject,
                    "question_ids": question_ids,
                    "shuffled_options": shuffled_options_master,
                    "target_tier": current_tier,
                    "status": "in_progress",
                }
            )
            .execute()
        )
    except (httpx.RequestError, Exception) as err:
        logger.warning(f"Database error inserting practice session: {err}")
        raise HTTPException(
            status_code=503,
            detail="Database connection temporarily unavailable.",
        )

    session_id = str(session_res.data[0]["id"])
    logger.info(
        f"Practice session {session_id} started for user {user_id}, subject {subject}, "
        f"{len(formatted)} questions, tier={current_tier}"
    )

    return PracticeStartResponse(
        session_id=session_id,
        subject=subject,
        target_tier=current_tier,
        total_questions=len(formatted),
        questions=formatted,
        saved_answers=[],
    )


def autosave_practice(user_id: str, payload: AutosaveAnswerRequest) -> AutosaveAnswerResponse:
    selected = (payload.selected_option or "").upper()
    if selected not in VALID_OPTIONS:
        raise HTTPException(status_code=400, detail="Choose A, B, C, D or E.")

    session = _load_session(user_id, payload.attempt_id)
    if session.get("status") != "in_progress":
        raise HTTPException(status_code=400, detail="This practice session is already submitted.")

    if payload.question_id not in [str(q) for q in (session["question_ids"] or [])]:
        raise HTTPException(
            status_code=400,
            detail="That question is not part of this practice session.",
        )

    try:
        _save_attempt_answer(user_id, payload.attempt_id, payload.question_id, selected, None)
    except Exception as err:
        logger.warning(f"Autosave DB write error (handled by client local backup): {err}")
        raise HTTPException(
            status_code=503,
            detail="Server backup unavailable. Answer saved locally on your device.",
        )

    return AutosaveAnswerResponse(
        status="saved",
        question_id=payload.question_id,
        selected_option=selected,
    )


def submit_practice(
    user_id: str,
    session_id: str,
    answers: List[AnswerSubmission],
) -> PracticeSubmitResponse:
    session = _load_session(user_id, session_id)

    q_ids = [str(q) for q in (session["question_ids"] or [])]
    shuffled_map = session["shuffled_options"] or {}
    q_dict = _questions_by_id(q_ids)

    chosen: Dict[str, str] = {}
    for row in _saved_rows(user_id, session_id):
        if row.get("selected_answer"):
            chosen[str(row["question_id"])] = str(row["selected_answer"]).upper()
    for ans in answers:
        chosen[str(ans.question_id)] = (ans.selected_option or "E").upper()

    if session.get("status") == "completed":
        return _build_submit_response(
            session, q_dict, chosen, float(session.get("score") or 0.0), session.get("completed_at") or ""
        )

    graded: Dict[str, Tuple[str, bool]] = {}
    correct_ids: Set[str] = set()
    for q_id in q_ids:
        if q_id not in chosen or q_id not in q_dict:
            continue
        label = chosen[q_id]
        if label not in VALID_OPTIONS:
            label = "E"
        is_correct = _grade_choice(q_dict[q_id], shuffled_map.get(q_id) or {}, label)
        graded[q_id] = (label, is_correct)
        if is_correct:
            correct_ids.add(q_id)

    total = len(q_ids)
    score = round((len(correct_ids) / total) * 100, 2) if total > 0 else 0.0
    now_str = datetime.now(timezone.utc).isoformat()

    try:
        claim = (
            supabase_admin.table("practice_sessions")
            .update({"status": "completed", "score": score, "completed_at": now_str})
            .eq("id", session_id)
            .eq("user_id", user_id)
            .eq("status", "in_progress")
            .execute()
        )
        if not claim.data:
            return _stored_result(user_id, _load_session(user_id, session_id))

        for q_id, (label, is_correct) in graded.items():
            _save_attempt_answer(user_id, session_id, q_id, label, is_correct)
            _mark_seen(user_id, q_id, session["subject"])

        new_tier = get_tier_from_score(score)
        supabase_admin.table("user_subjects").update(
            {"current_tier": new_tier, "updated_at": now_str}
        ).eq("user_id", user_id).eq("subject", session["subject"]).execute()

    except (httpx.RequestError, Exception) as err:
        logger.error(f"Error submitting practice session: {err}")
        raise HTTPException(
            status_code=503,
            detail="Network error while grading. Please try submitting again in a moment.",
        )

    logger.info(
        f"Practice completed for user {user_id}: score={score}%, "
        f"{session['target_tier']} -> {new_tier}"
    )
    return _build_submit_response(session, q_dict, chosen, score, now_str)