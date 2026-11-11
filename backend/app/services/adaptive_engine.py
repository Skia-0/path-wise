import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple
from fastapi import HTTPException

from app.db.supabase_client import supabase_admin
from app.models.diagnostic import (
    DiagnosticQuestionResponse,
    QuestionOption,
    TopicBreakdown,
    DiagnosticStartResponse,
    DiagnosticSubmitResponse,
    AnswerSubmission,
)
from app.models.practice import (
    PracticeStartResponse,
    PracticeSubmitResponse,
    AutosaveAnswerRequest,
    AutosaveAnswerResponse,
)
from app.utils.logger import logger

# Diagnostic attempts expire after this many days without activity.
# Starting (resuming), autosaving, or submitting pushes the deadline forward.
DIAGNOSTIC_INACTIVITY_DAYS = 14
EXPIRED_MESSAGE = "This diagnostic expired after 14 days of inactivity. Please start a new one."
DIAGNOSTIC_QUESTION_COUNT = 15


def get_waec_grade(score: float) -> str:
    if score >= 75:
        return "A1"
    if score >= 70:
        return "B2"
    if score >= 65:
        return "B3"
    if score >= 60:
        return "C4"
    if score >= 55:
        return "C5"
    if score >= 50:
        return "C6"
    if score >= 45:
        return "D7"
    if score >= 40:
        return "E8"
    return "F9"


def get_tier_from_score(score: float) -> str:
    if score >= 70.0:
        return "Advanced"
    if score >= 40.0:
        return "Intermediate"
    return "Beginner"


def _topic_fields(q: Dict[str, Any]) -> Tuple[str, str]:
    """
    Returns (topic_key, topic_name) from the canonical_topics join.
    canonical_topics has id and topic_name only (no code column), so id is the grouping key.
    """
    topic_info = q.get("canonical_topics") or {}
    if isinstance(topic_info, list):
        topic_info = topic_info[0] if topic_info else {}
    key = str(topic_info.get("id") or q.get("topic_id") or "GEN")
    name = topic_info.get("topic_name") or "General"
    return key, name


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_expired(attempt: Dict[str, Any]) -> bool:
    expires = _parse_ts(attempt.get("expires_at"))
    if expires is None:
        return False
    return expires <= datetime.now(timezone.utc)


def _inactivity_deadline() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=DIAGNOSTIC_INACTIVITY_DAYS)).isoformat()


def _expire_attempt(attempt_id: str) -> None:
    try:
        supabase_admin.table("diagnostic_attempts").update(
            {"status": "expired"}
        ).eq("id", attempt_id).execute()
    except Exception as e:
        # The expiry check uses expires_at, so the attempt is still blocked if this write fails.
        logger.warning(f"Could not mark diagnostic attempt {attempt_id} as expired: {e}")


def _extend_deadline(attempt_id: str) -> str:
    deadline = _inactivity_deadline()
    supabase_admin.table("diagnostic_attempts").update(
        {"expires_at": deadline}
    ).eq("id", attempt_id).execute()
    return deadline


def _require_live_diagnostic(user_id: str, attempt_id: str) -> Dict[str, Any]:
    """Loads a diagnostic attempt owned by this user and rejects completed or expired attempts."""
    res = (
        supabase_admin.table("diagnostic_attempts")
        .select("*")
        .eq("id", attempt_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Diagnostic attempt not found")

    attempt = res.data[0]
    if attempt.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Diagnostic attempt already submitted")
    if attempt.get("status") == "expired" or _is_expired(attempt):
        if attempt.get("status") != "expired":
            _expire_attempt(attempt_id)
        raise HTTPException(status_code=410, detail=EXPIRED_MESSAGE)
    return attempt


def _save_attempt_answer(
    user_id: str,
    attempt_id: str,
    question_id: str,
    selected_label: str,
    is_correct: Optional[bool],
) -> None:
    """
    Saves one answer without relying on a unique constraint:
    updates the existing row for this user, attempt and question, or inserts a new one.
    Matches the attempt_answers table: selected_answer, is_correct, answered_at.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    values = {
        "selected_answer": selected_label,
        "is_correct": is_correct,
        "answered_at": now_str,
    }

    existing = (
        supabase_admin.table("attempt_answers")
        .select("id")
        .eq("user_id", user_id)
        .eq("attempt_id", attempt_id)
        .eq("question_id", question_id)
        .execute()
    )

    if existing.data:
        supabase_admin.table("attempt_answers").update(values).eq(
            "id", existing.data[0]["id"]
        ).execute()
    else:
        supabase_admin.table("attempt_answers").insert(
            {
                "user_id": user_id,
                "attempt_id": attempt_id,
                "question_id": question_id,
                **values,
            }
        ).execute()


def _mark_seen(user_id: str, question_id: str, subject: str) -> None:
    """
    Records that a user has seen a question, without relying on a unique constraint.
    seen_questions requires subject, so it is passed in.
    """
    existing = (
        supabase_admin.table("seen_questions")
        .select("question_id")
        .eq("user_id", user_id)
        .eq("question_id", question_id)
        .execute()
    )
    if not existing.data:
        supabase_admin.table("seen_questions").insert(
            {"user_id": user_id, "question_id": question_id, "subject": subject}
        ).execute()


def _select_diagnostic_questions(subject: str, count: int = DIAGNOSTIC_QUESTION_COUNT) -> List[Dict[str, Any]]:
    """
    Picks up to `count` questions spread across the subject's topics.
    Questions are grouped by topic, shuffled within each group, and dealt out
    one topic at a time in a random topic order, so every topic gets a turn
    before any topic gets a second question.
    """
    res = (
        supabase_admin.table("questions")
        .select("*, canonical_topics(*)")
        .eq("subject", subject)
        .limit(1000)
        .execute()
    )
    rows = res.data or []

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for q in rows:
        key, _ = _topic_fields(q)
        groups.setdefault(key, []).append(q)

    for group in groups.values():
        random.shuffle(group)

    topic_keys = list(groups.keys())
    random.shuffle(topic_keys)

    selected: List[Dict[str, Any]] = []
    while len(selected) < count and any(groups[k] for k in topic_keys):
        for key in topic_keys:
            if groups[key] and len(selected) < count:
                selected.append(groups[key].pop())
    return selected


def shuffle_options_for_question(q: Dict[str, Any]) -> Tuple[List[QuestionOption], Dict[str, str]]:
    """
    Shuffle A-D server-side. Map display label -> original label.
    Always append Option E = "I don't know".
    """
    orig_options = [
        ("A", q.get("option_a") or ""),
        ("B", q.get("option_b") or ""),
        ("C", q.get("option_c") or ""),
        ("D", q.get("option_d") or ""),
    ]
    random.shuffle(orig_options)

    labels = ["A", "B", "C", "D"]
    display_options: List[QuestionOption] = []
    shuffled_mapping: Dict[str, str] = {}

    for i, (orig_label, opt_text) in enumerate(orig_options):
        disp_label = labels[i]
        display_options.append(QuestionOption(label=disp_label, text=opt_text))
        shuffled_mapping[disp_label] = orig_label

    display_options.append(QuestionOption(label="E", text="I don't know"))
    shuffled_mapping["E"] = "E"
    return display_options, shuffled_mapping


def _rebuild_options_from_mapping(q: Dict[str, Any], q_map: Dict[str, str]) -> List[QuestionOption]:
    opts: List[QuestionOption] = []
    for lbl in ["A", "B", "C", "D"]:
        orig = q_map.get(lbl, lbl)
        if orig == "E":
            text = "I don't know"
        else:
            text = q.get(f"option_{orig.lower()}") or ""
        opts.append(QuestionOption(label=lbl, text=text))
    opts.append(QuestionOption(label="E", text="I don't know"))
    return opts


def _format_questions(
    question_ids: List[str],
    q_dict: Dict[str, Any],
    shuffled_map: Dict[str, Any],
) -> List[DiagnosticQuestionResponse]:
    formatted: List[DiagnosticQuestionResponse] = []
    for idx, q_id in enumerate(question_ids, start=1):
        q = q_dict.get(q_id)
        if not q:
            continue
        q_map = shuffled_map.get(q_id, {}) or {}
        opts = _rebuild_options_from_mapping(q, q_map)
        t_code, t_name = _topic_fields(q)
        formatted.append(
            DiagnosticQuestionResponse(
                id=q["id"],
                question_number=idx,
                question_text=q.get("question_text") or "",
                options=opts,
                diagram_url=q.get("diagram_url"),
                topic_code=t_code,
                topic_name=t_name,
            )
        )
    return formatted


def start_diagnostic(user_id: str, subject: str) -> DiagnosticStartResponse:
    # Retakes are blocked: once a subject's diagnostic is completed, it cannot be started again.
    done = (
        supabase_admin.table("diagnostic_attempts")
        .select("id")
        .eq("user_id", user_id)
        .eq("subject", subject)
        .eq("status", "completed")
        .limit(1)
        .execute()
    )
    if done.data:
        raise HTTPException(
            status_code=409,
            detail=f"You have already completed the {subject} diagnostic. Retakes are not allowed.",
        )

    # Resume the open attempt if it is still live. Expired open attempts are closed.
    existing = (
        supabase_admin.table("diagnostic_attempts")
        .select("*")
        .eq("user_id", user_id)
        .eq("subject", subject)
        .eq("status", "in_progress")
        .execute()
    )

    live_attempt: Optional[Dict[str, Any]] = None
    for att in existing.data or []:
        if _is_expired(att):
            _expire_attempt(att["id"])
        elif live_attempt is None:
            live_attempt = att

    if live_attempt:
        deadline = _extend_deadline(live_attempt["id"])
        q_ids = live_attempt["question_ids"]
        shuffled_map = live_attempt["shuffled_options"] or {}

        questions_res = (
            supabase_admin.table("questions")
            .select("*, canonical_topics(*)")
            .in_("id", q_ids)
            .execute()
        )
        q_dict = {q["id"]: q for q in (questions_res.data or [])}
        formatted_questions = _format_questions(q_ids, q_dict, shuffled_map)

        # Return the choices already saved for this attempt so the screen can restore them.
        saved_res = (
            supabase_admin.table("attempt_answers")
            .select("question_id, selected_answer")
            .eq("user_id", user_id)
            .eq("attempt_id", live_attempt["id"])
            .execute()
        )
        saved_answers = [
            AnswerSubmission(
                question_id=str(row["question_id"]),
                selected_option=str(row["selected_answer"]).upper(),
            )
            for row in (saved_res.data or [])
            if row.get("selected_answer")
        ]

        return DiagnosticStartResponse(
            attempt_id=live_attempt["id"],
            subject=subject,
            total_questions=len(formatted_questions),
            expires_at=deadline,
            questions=formatted_questions,
            saved_answers=saved_answers,
        )

    # New diagnostic: pick questions spread across the subject's topics
    raw_questions = _select_diagnostic_questions(subject)
    if len(raw_questions) < 5:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient questions in database for {subject}",
        )

    question_ids: List[str] = []
    shuffled_options_master: Dict[str, Any] = {}
    formatted_questions: List[DiagnosticQuestionResponse] = []

    for idx, q in enumerate(raw_questions, start=1):
        q_id = q["id"]
        question_ids.append(q_id)
        opts, mapping = shuffle_options_for_question(q)
        shuffled_options_master[q_id] = mapping

        t_code, t_name = _topic_fields(q)

        formatted_questions.append(
            DiagnosticQuestionResponse(
                id=q_id,
                question_number=idx,
                question_text=q.get("question_text") or "",
                options=opts,
                diagram_url=q.get("diagram_url"),
                topic_code=t_code,
                topic_name=t_name,
            )
        )

    expires_at = _inactivity_deadline()
    attempt_res = (
        supabase_admin.table("diagnostic_attempts")
        .insert(
            {
                "user_id": user_id,
                "subject": subject,
                "question_ids": question_ids,
                "shuffled_options": shuffled_options_master,
                "status": "in_progress",
                "expires_at": expires_at,
            }
        )
        .execute()
    )
    attempt_id = attempt_res.data[0]["id"]
    logger.info(f"Diagnostic started for user {user_id}, subject {subject}, attempt {attempt_id}")

    return DiagnosticStartResponse(
        attempt_id=attempt_id,
        subject=subject,
        total_questions=len(formatted_questions),
        expires_at=expires_at,
        questions=formatted_questions,
        saved_answers=[],
    )


def submit_diagnostic(
    user_id: str,
    attempt_id: str,
    answers: List[AnswerSubmission],
) -> DiagnosticSubmitResponse:
    attempt = _require_live_diagnostic(user_id, attempt_id)

    subject = attempt["subject"]
    shuffled_map = attempt["shuffled_options"] or {}
    q_ids = attempt["question_ids"] or []

    questions_res = (
        supabase_admin.table("questions")
        .select("*, canonical_topics(*)")
        .in_("id", q_ids)
        .execute()
    )
    q_dict = {q["id"]: q for q in (questions_res.data or [])}

    # Answers saved during the diagnostic (autosave) count too, not only the ones sent with submit.
    saved_res = (
        supabase_admin.table("attempt_answers")
        .select("question_id, selected_answer")
        .eq("user_id", user_id)
        .eq("attempt_id", attempt_id)
        .execute()
    )
    chosen: Dict[str, str] = {}
    for row in saved_res.data or []:
        if row.get("selected_answer"):
            chosen[str(row["question_id"])] = str(row["selected_answer"]).upper()
    # Answers sent with submit override the saved ones.
    for ans in answers:
        chosen[str(ans.question_id)] = (ans.selected_option or "E").upper()

    correct_count = 0
    total_count = len(q_ids)
    topic_stats: Dict[str, Dict[str, Any]] = {}

    for q_id in q_ids:
        q = q_dict.get(q_id)
        if not q:
            continue

        t_code, t_name = _topic_fields(q)
        if t_code not in topic_stats:
            topic_stats[t_code] = {"name": t_name, "correct": 0, "total": 0}
        # Every question in the attempt counts toward the topic denominator, answered or not.
        topic_stats[t_code]["total"] += 1

        if q_id not in chosen:
            continue

        selected_label = chosen[q_id]
        orig_selected = (shuffled_map.get(q_id) or {}).get(selected_label, "E")

        is_correct = False
        correct_option = (q.get("correct_option") or "").upper()
        if orig_selected != "E" and orig_selected == correct_option:
            is_correct = True
            correct_count += 1
            topic_stats[t_code]["correct"] += 1

        _save_attempt_answer(user_id, attempt_id, q_id, selected_label, is_correct)
        _mark_seen(user_id, q_id, subject)

    overall_score = round((correct_count / total_count) * 100, 2) if total_count > 0 else 0.0
    assigned_tier = get_tier_from_score(overall_score)
    waec_grade = get_waec_grade(overall_score)
    now_str = datetime.now(timezone.utc).isoformat()

    supabase_admin.table("diagnostic_attempts").update(
        {
            "status": "completed",
            "score": overall_score,
            "assigned_tier": assigned_tier,
            "completed_at": now_str,
        }
    ).eq("id", attempt_id).execute()

    supabase_admin.table("user_subjects").update(
        {
            "current_tier": assigned_tier,
            "diagnostic_completed": True,
            "updated_at": now_str,
        }
    ).eq("user_id", user_id).eq("subject", subject).execute()

    topic_breakdown = [
        TopicBreakdown(
            topic_code=code,
            topic_name=data["name"],
            correct_count=data["correct"],
            total_count=data["total"],
            percentage=round((data["correct"] / data["total"]) * 100, 2) if data["total"] > 0 else 0.0,
        )
        for code, data in topic_stats.items()
    ]

    logger.info(
        f"Diagnostic completed for user {user_id}: score={overall_score}%, tier={assigned_tier}, grade={waec_grade}"
    )

    return DiagnosticSubmitResponse(
        attempt_id=attempt_id,
        subject=subject,
        score=overall_score,
        assigned_tier=assigned_tier,
        waec_grade=waec_grade,
        completed_at=now_str,
        topic_breakdown=topic_breakdown,
    )


def autosave_answer(user_id: str, payload: AutosaveAnswerRequest) -> AutosaveAnswerResponse:
    selected = (payload.selected_option or "E").upper()

    # Diagnostic autosaves must belong to a live attempt, and each save extends the deadline.
    if (payload.session_type or "").lower() == "diagnostic":
        _require_live_diagnostic(user_id, payload.attempt_id)
        _extend_deadline(payload.attempt_id)

    # is_correct is set when the attempt is submitted, so autosave leaves it empty.
    _save_attempt_answer(user_id, payload.attempt_id, payload.question_id, selected, None)

    return AutosaveAnswerResponse(
        status="saved",
        question_id=payload.question_id,
        selected_option=selected,
    )


def start_practice(user_id: str, subject: str, num_questions: int = 10) -> PracticeStartResponse:
    if num_questions < 10:
        raise HTTPException(status_code=400, detail="Minimum practice session size is 10 questions")

    sub_res = (
        supabase_admin.table("user_subjects")
        .select("current_tier, diagnostic_completed")
        .eq("user_id", user_id)
        .eq("subject", subject)
        .execute()
    )
    if not sub_res.data:
        raise HTTPException(status_code=400, detail=f"Subject not enrolled: {subject}")

    current_tier = sub_res.data[0].get("current_tier") or "Beginner"

    seen_res = (
        supabase_admin.table("seen_questions")
        .select("question_id")
        .eq("user_id", user_id)
        .execute()
    )
    seen_ids = {r["question_id"] for r in (seen_res.data or [])}

    questions_res = (
        supabase_admin.table("questions")
        .select("*, canonical_topics(*)")
        .eq("subject", subject)
        .limit(max(num_questions * 3, 30))
        .execute()
    )
    raw_questions = questions_res.data or []
    unseen = [q for q in raw_questions if q["id"] not in seen_ids]
    pool = unseen if len(unseen) >= num_questions else raw_questions
    random.shuffle(pool)
    selected_raw = pool[:num_questions]

    if len(selected_raw) < 10:
        raise HTTPException(status_code=400, detail="Not enough questions available for practice")

    question_ids: List[str] = []
    shuffled_options_master: Dict[str, Any] = {}
    formatted_questions: List[DiagnosticQuestionResponse] = []

    for idx, q in enumerate(selected_raw, start=1):
        q_id = q["id"]
        question_ids.append(q_id)
        opts, mapping = shuffle_options_for_question(q)
        shuffled_options_master[q_id] = mapping
        t_code, t_name = _topic_fields(q)

        formatted_questions.append(
            DiagnosticQuestionResponse(
                id=q_id,
                question_number=idx,
                question_text=q.get("question_text") or "",
                options=opts,
                diagram_url=q.get("diagram_url"),
                topic_code=t_code,
                topic_name=t_name,
            )
        )

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
    session_id = session_res.data[0]["id"]
    logger.info(f"Practice session {session_id} started for user {user_id}, tier={current_tier}")

    return PracticeStartResponse(
        session_id=session_id,
        subject=subject,
        target_tier=current_tier,
        total_questions=len(formatted_questions),
        questions=formatted_questions,
    )


def submit_practice(
    user_id: str,
    session_id: str,
    answers: List[AnswerSubmission],
) -> PracticeSubmitResponse:
    session_res = (
        supabase_admin.table("practice_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Practice session not found")

    session = session_res.data[0]
    if session["status"] == "completed":
        raise HTTPException(status_code=400, detail="Practice session already submitted")

    shuffled_map = session["shuffled_options"] or {}
    q_ids = session["question_ids"] or []
    subject = session["subject"]
    target_tier = session["target_tier"]

    questions_res = (
        supabase_admin.table("questions")
        .select("*, canonical_topics(*)")
        .in_("id", q_ids)
        .execute()
    )
    q_dict = {q["id"]: q for q in (questions_res.data or [])}

    correct_count = 0
    total_count = len(q_ids)
    topic_stats: Dict[str, Dict[str, Any]] = {}

    for ans in answers:
        q_id = ans.question_id
        q = q_dict.get(q_id)
        if not q:
            continue

        t_code, t_name = _topic_fields(q)
        if t_code not in topic_stats:
            topic_stats[t_code] = {"name": t_name, "correct": 0, "total": 0}
        topic_stats[t_code]["total"] += 1

        selected_label = (ans.selected_option or "E").upper()
        orig_selected = (shuffled_map.get(q_id) or {}).get(selected_label, "E")

        is_correct = False
        correct_option = (q.get("correct_option") or "").upper()
        if orig_selected != "E" and orig_selected == correct_option:
            is_correct = True
            correct_count += 1
            topic_stats[t_code]["correct"] += 1

        _save_attempt_answer(user_id, session_id, q_id, selected_label, is_correct)
        _mark_seen(user_id, q_id, subject)

    overall_score = round((correct_count / total_count) * 100, 2) if total_count > 0 else 0.0
    new_tier = get_tier_from_score(overall_score)
    waec_grade = get_waec_grade(overall_score)
    now_str = datetime.now(timezone.utc).isoformat()

    supabase_admin.table("practice_sessions").update(
        {
            "status": "completed",
            "score": overall_score,
            "completed_at": now_str,
        }
    ).eq("id", session_id).execute()

    supabase_admin.table("user_subjects").update(
        {
            "current_tier": new_tier,
            "updated_at": now_str,
        }
    ).eq("user_id", user_id).eq("subject", subject).execute()

    topic_breakdown = [
        TopicBreakdown(
            topic_code=code,
            topic_name=data["name"],
            correct_count=data["correct"],
            total_count=data["total"],
            percentage=round((data["correct"] / data["total"]) * 100, 2) if data["total"] > 0 else 0.0,
        )
        for code, data in topic_stats.items()
    ]

    logger.info(
        f"Practice completed for user {user_id}: score={overall_score}%, {target_tier} -> {new_tier}"
    )

    return PracticeSubmitResponse(
        session_id=session_id,
        subject=subject,
        score=overall_score,
        target_tier=target_tier,
        new_tier=new_tier,
        waec_grade=waec_grade,
        completed_at=now_str,
        topic_breakdown=topic_breakdown,
    )