from typing import Any, Dict, List, Tuple
from app.db.supabase_client import supabase_admin
from app.services.bkt_engine import update_bkt, DEFAULT_P_INIT
from app.utils.logger import logger


def _get_topic_info(q: Dict[str, Any]) -> Tuple[str, str]:
    """Safely extracts (topic_code, topic_name) regardless of canonical_topics shape."""
    ct = q.get("canonical_topics")
    if isinstance(ct, list) and len(ct) > 0:
        ct = ct[0]
    if isinstance(ct, dict):
        code = ct.get("topic_code") or ct.get("code") or ct.get("id") or "GEN"
        name = ct.get("topic_name") or ct.get("name") or ct.get("title") or "General Topic"
        return str(code), str(name)

    code = q.get("topic_code") or q.get("topic_id") or "GEN"
    name = q.get("topic_name") or q.get("topic") or "General Topic"
    return str(code), str(name)


def get_study_path(user_id: str, subject: str) -> Dict[str, Any]:
    """
    Calculates BKT skill mastery probabilities P(L) for a user and subject across diagnostic and practice.
    Returns focus topics (<60% BKT mastery) and full BKT topic mastery breakdown.
    """
    try:
        q_res = (
            supabase_admin.table("questions")
            .select("id, topic_id, canonical_topics(*)")
            .eq("subject", subject)
            .execute()
        )
        questions = q_res.data or []
        if not questions:
            return {"subject": subject, "focus_topics": [], "all_topics": []}

        q_map = {str(q["id"]): q for q in questions}
        q_ids = list(q_map.keys())

        # Query attempt answers without referencing missing created_at column
        answers_res = (
            supabase_admin.table("attempt_answers")
            .select("question_id, is_correct")
            .eq("user_id", user_id)
            .in_("question_id", q_ids)
            .execute()
        )
        answers = answers_res.data or []

        stats: Dict[str, Dict[str, Any]] = {}

        for q in questions:
            code, name = _get_topic_info(q)
            if code not in stats:
                stats[code] = {
                    "topic_code": code,
                    "topic_name": name,
                    "bkt_p_know": DEFAULT_P_INIT,  # Starts at standard P(L0) = 0.20 (20%)
                    "correct": 0,
                    "total": 0,
                }

        # Sequential BKT update per answer event
        for ans in answers:
            q_id = str(ans.get("question_id"))
            q = q_map.get(q_id)
            if not q:
                continue
            code, _ = _get_topic_info(q)
            if code in stats:
                is_corr = bool(ans.get("is_correct"))
                stats[code]["total"] += 1
                if is_corr:
                    stats[code]["correct"] += 1
                # Update BKT probability
                stats[code]["bkt_p_know"] = update_bkt(stats[code]["bkt_p_know"], is_corr)

        topic_mastery: List[Dict[str, Any]] = []
        for code, data in stats.items():
            tot = data["total"]
            raw_pct = round((data["correct"] / tot) * 100, 1) if tot > 0 else 0.0
            bkt_pct = round(data["bkt_p_know"] * 100, 1)

            topic_mastery.append(
                {
                    "topic_code": code,
                    "topic_name": data["topic_name"],
                    "correct_count": data["correct"],
                    "total_count": tot,
                    "percentage": bkt_pct,  # BKT probability percentage
                    "raw_accuracy": raw_pct,
                    "has_attempted": tot > 0,
                }
            )

        # Sort topics by BKT probability ascending to identify weakest focus areas
        weak_candidates = sorted(topic_mastery, key=lambda x: (x["percentage"], x["total_count"]))
        focus = [t for t in weak_candidates if t["percentage"] < 60.0 or not t["has_attempted"]][:3]

        if not focus and weak_candidates:
            focus = weak_candidates[:3]

        return {
            "subject": subject,
            "focus_topics": [
                {
                    "topic_code": f["topic_code"],
                    "topic_name": f["topic_name"],
                    "percentage": f["percentage"],
                    "has_attempted": f["has_attempted"],
                }
                for f in focus
            ],
            "all_topics": topic_mastery,
        }
    except Exception as err:
        logger.error(f"Error calculating study path for {user_id} ({subject}): {err}")
        return {"subject": subject, "focus_topics": [], "all_topics": []}