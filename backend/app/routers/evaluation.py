from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any

from app.models.evaluation import SUSSubmission, EventLogItem
from app.services.auth_service import get_current_user
from app.services.evaluation_service import save_sus_response, get_user_sus_status, log_app_event

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])


def _extract_user_id(user: Any) -> str:
    """Safely extracts user ID whether current_user is a Pydantic model or dictionary."""
    if hasattr(user, "id") and getattr(user, "id"):
        return str(getattr(user, "id"))
    if isinstance(user, dict):
        return str(user.get("id") or user.get("sub") or "")
    return str(user)


@router.post("/sus")
async def submit_sus(
    submission: SUSSubmission,
    current_user: Any = Depends(get_current_user)
) -> Dict[str, Any]:
    try:
        user_id = _extract_user_id(current_user)
        result = await save_sus_response(user_id, submission)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error submitting usability evaluation: {str(e)}"
        )


@router.get("/sus/status")
async def check_sus_status(
    current_user: Any = Depends(get_current_user)
) -> Dict[str, Any]:
    try:
        user_id = _extract_user_id(current_user)
        return await get_user_sus_status(user_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking survey status: {str(e)}"
        )


@router.post("/event")
async def record_event(
    item: EventLogItem,
    current_user: Any = Depends(get_current_user)
) -> Dict[str, str]:
    try:
        user_id = _extract_user_id(current_user)
        await log_app_event(user_id, item.event_type, item.metadata)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "degraded"}