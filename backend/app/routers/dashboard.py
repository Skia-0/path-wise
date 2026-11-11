from datetime import datetime, timezone
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.supabase_client import get_supabase_client, supabase_admin
from app.models.auth import UserProfileResponse
from app.services.auth_service import get_current_user
from app.utils.logger import logger

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])

SubjectName = Literal["Core Mathematics", "Elective Physics"]
DEFAULT_TIER = "Beginner"


class SubjectStatus(BaseModel):
    subject: str
    current_tier: str
    diagnostic_completed: bool
    has_open_diagnostic: bool  # started, not submitted, not expired: "Continue" for the diagnostic
    has_open_practice: bool    # started, not submitted: "Continue" for practice


class DashboardSubjectsResponse(BaseModel):
    subjects: List[SubjectStatus]


class SubjectChangeRequest(BaseModel):
    subject: SubjectName


class SubjectChangeResponse(BaseModel):
    subject: str
    action: str  # "hidden", "added" or "restored"


def _is_live(attempt) -> bool:
    """Same rule as the diagnostic engine: no expiry date, or an expiry date still in the future."""
    raw = attempt.get("expires_at")
    if not raw:
        return True
    try:
        expires = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > datetime.now(timezone.utc)


@router.get("/subjects", response_model=DashboardSubjectsResponse)
def get_subjects(current_user: UserProfileResponse = Depends(get_current_user)):
    """Returns the signed-in student's visible subjects with tier and open-session status. Read-only."""
    supabase = get_supabase_client()
    try:
        subjects_resp = (
            supabase.table("user_subjects")
            .select("subject, current_tier, diagnostic_completed, archived")
            .eq("user_id", current_user.id)
            .execute()
        )
        open_diag_resp = (
            supabase.table("diagnostic_attempts")
            .select("subject, expires_at")
            .eq("user_id", current_user.id)
            .eq("status", "in_progress")
            .execute()
        )
        open_practice_resp = (
            supabase.table("practice_sessions")
            .select("subject")
            .eq("user_id", current_user.id)
            .eq("status", "in_progress")
            .execute()
        )
    except Exception as e:
        logger.error(f"Dashboard subjects lookup failed for {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not load subjects right now. Please try again.",
        )

    open_diagnostic_subjects = {
        row.get("subject")
        for row in (open_diag_resp.data or [])
        if _is_live(row)
    }
    open_practice_subjects = {
        row.get("subject")
        for row in (open_practice_resp.data or [])
    }

    visible_rows = [row for row in (subjects_resp.data or []) if not row.get("archived")]

    subjects = [
        SubjectStatus(
            subject=row.get("subject") or "",
            current_tier=row.get("current_tier") or DEFAULT_TIER,
            diagnostic_completed=bool(row.get("diagnostic_completed")),
            has_open_diagnostic=(row.get("subject") in open_diagnostic_subjects),
            has_open_practice=(row.get("subject") in open_practice_subjects),
        )
        for row in visible_rows
    ]
    return DashboardSubjectsResponse(subjects=subjects)


@router.post("/subjects/archive", response_model=SubjectChangeResponse)
def archive_subject(
    payload: SubjectChangeRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    """
    Hides a subject from the dashboard. Its diagnostic and practice data are kept,
    and restoring the subject brings back any open session.
    """
    user_id = current_user.id
    try:
        rows_res = (
            supabase_admin.table("user_subjects")
            .select("subject, archived")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as e:
        logger.error(f"Archive lookup failed for {user_id}: {e}")
        raise HTTPException(status_code=503, detail="Could not update your subjects right now. Please try again.")

    rows = rows_res.data or []
    target = next((r for r in rows if r.get("subject") == payload.subject), None)
    if target is None:
        raise HTTPException(status_code=404, detail="That subject is not on your account.")
    if target.get("archived"):
        return SubjectChangeResponse(subject=payload.subject, action="hidden")

    visible_count = sum(1 for r in rows if not r.get("archived"))
    if visible_count <= 1:
        raise HTTPException(
            status_code=400,
            detail="You need at least one subject on your dashboard, so this one cannot be hidden.",
        )

    try:
        supabase_admin.table("user_subjects").update(
            {"archived": True, "updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("user_id", user_id).eq("subject", payload.subject).execute()
    except Exception as e:
        logger.error(f"Archive update failed for {user_id}: {e}")
        raise HTTPException(status_code=503, detail="Could not hide this subject right now. Please try again.")

    logger.info(f"User {user_id} hid subject {payload.subject}")
    return SubjectChangeResponse(subject=payload.subject, action="hidden")


@router.post("/subjects/add", response_model=SubjectChangeResponse)
def add_subject(
    payload: SubjectChangeRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    """Adds a subject to the dashboard. A hidden subject is restored with its data intact."""
    user_id = current_user.id
    now_str = datetime.now(timezone.utc).isoformat()
    try:
        existing_res = (
            supabase_admin.table("user_subjects")
            .select("subject, archived")
            .eq("user_id", user_id)
            .eq("subject", payload.subject)
            .execute()
        )
    except Exception as e:
        logger.error(f"Add-subject lookup failed for {user_id}: {e}")
        raise HTTPException(status_code=503, detail="Could not add the subject right now. Please try again.")

    existing = (existing_res.data or [None])[0]

    if existing is not None:
        if not existing.get("archived"):
            raise HTTPException(
                status_code=409,
                detail=f"{payload.subject} is already on your dashboard.",
            )
        try:
            supabase_admin.table("user_subjects").update(
                {"archived": False, "updated_at": now_str}
            ).eq("user_id", user_id).eq("subject", payload.subject).execute()
        except Exception as e:
            logger.error(f"Restore failed for {user_id}: {e}")
            raise HTTPException(status_code=503, detail="Could not restore the subject right now. Please try again.")
        logger.info(f"User {user_id} restored subject {payload.subject}")
        return SubjectChangeResponse(subject=payload.subject, action="restored")

    try:
        supabase_admin.table("user_subjects").insert(
            {
                "user_id": user_id,
                "subject": payload.subject,
                "current_tier": DEFAULT_TIER,
                "diagnostic_completed": False,
                "archived": False,
                "updated_at": now_str,
            }
        ).execute()
    except Exception as e:
        logger.error(f"Add-subject insert failed for {user_id}: {e}")
        raise HTTPException(status_code=503, detail="Could not add the subject right now. Please try again.")

    logger.info(f"User {user_id} added subject {payload.subject}")
    return SubjectChangeResponse(subject=payload.subject, action="added")