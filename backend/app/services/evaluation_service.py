import logging
from typing import Dict, Any, Optional
from app.db.supabase_client import get_supabase_admin
from app.models.evaluation import SUSSubmission, EventLogItem

logger = logging.getLogger("pathwise")

def calculate_sus_score(submission: SUSSubmission) -> float:
    """
    Standard Brooke (1996) System Usability Scale (SUS) Score Calculation:
    - Odd questions (1, 3, 5, 7, 9): Score - 1
    - Even questions (2, 4, 6, 8, 10): 5 - Score
    - Sum of contribution scores multiplied by 2.5 yields final score (0 - 100).
    """
    q = [
        submission.q1, submission.q2, submission.q3, submission.q4, submission.q5,
        submission.q6, submission.q7, submission.q8, submission.q9, submission.q10
    ]
    
    contributions = []
    for idx, val in enumerate(q):
        if idx % 2 == 0:  # Odd questions (0-indexed: 0, 2, 4, 6, 8 -> Q1, Q3, Q5, Q7, Q9)
            contributions.append(val - 1)
        else:  # Even questions (0-indexed: 1, 3, 5, 7, 9 -> Q2, Q4, Q6, Q8, Q10)
            contributions.append(5 - val)
            
    raw_sum = sum(contributions)
    sus_score = round(raw_sum * 2.5, 2)
    return sus_score

async def save_sus_response(user_id: str, submission: SUSSubmission) -> Dict[str, Any]:
    supabase = get_supabase_admin()
    sus_score = calculate_sus_score(submission)
    
    record = {
        "user_id": user_id,
        "q1": submission.q1,
        "q2": submission.q2,
        "q3": submission.q3,
        "q4": submission.q4,
        "q5": submission.q5,
        "q6": submission.q6,
        "q7": submission.q7,
        "q8": submission.q8,
        "q9": submission.q9,
        "q10": submission.q10,
        "sus_score": sus_score,
        "feedback": (submission.feedback or "").strip()
    }
    
    res = supabase.table("sus_responses").insert(record).execute()
    
    if not res.data:
        raise RuntimeError("Failed to record SUS response in database.")
        
    logger.info(f"SUS survey recorded for user {user_id}. Final score: {sus_score}/100")
    
    # Also log an event for evaluation timeline tracking
    await log_app_event(user_id, "sus_submitted", {"sus_score": sus_score})
    
    return {"sus_score": sus_score, "message": "Thank you! Your feedback has been recorded."}

async def get_user_sus_status(user_id: str) -> Dict[str, Any]:
    supabase = get_supabase_admin()
    res = supabase.table("sus_responses").select("id, sus_score, created_at").eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
    
    completed = len(res.data) > 0
    latest = res.data[0] if completed else None
    
    return {
        "completed": completed,
        "latest_score": latest["sus_score"] if latest else None,
        "submitted_at": latest["created_at"] if latest else None
    }

async def log_app_event(user_id: Optional[str], event_type: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    try:
        supabase = get_supabase_admin()
        event_record = {
            "user_id": user_id,
            "event_type": event_type,
            "metadata": metadata or {}
        }
        supabase.table("app_events").insert(event_record).execute()
    except Exception as e:
        logger.warning(f"Failed to log app event '{event_type}': {e}")