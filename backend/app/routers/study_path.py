from fastapi import APIRouter, Depends, HTTPException

from app.routers.auth import get_current_user
from app.services.study_path_service import get_study_path

router = APIRouter(prefix="/api/v1/studypath", tags=["StudyPath"])


@router.get("/{subject}")
def get_user_study_path(
    subject: str,
    current_user=Depends(get_current_user),
):
    valid_subjects = {"Core Mathematics", "Elective Physics"}
    if subject not in valid_subjects:
        raise HTTPException(status_code=400, detail="Invalid subject")

    return get_study_path(user_id=str(current_user.id), subject=subject)