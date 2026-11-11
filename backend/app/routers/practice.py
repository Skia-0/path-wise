from fastapi import APIRouter, Depends
from app.models.auth import UserProfileResponse
from app.services.auth_service import get_current_user
from app.models.practice import (
    PracticeStartRequest,
    PracticeStartResponse,
    PracticeSubmitRequest,
    PracticeSubmitResponse,
    AutosaveAnswerRequest,
    AutosaveAnswerResponse,
)
from app.services.practice_service import start_practice, submit_practice, autosave_practice

router = APIRouter(prefix="/api/v1/practice", tags=["Adaptive Practice Engine"])


@router.post("/start", response_model=PracticeStartResponse)
def handle_start_practice(
    payload: PracticeStartRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    return start_practice(
        user_id=current_user.id,
        subject=payload.subject,
        num_questions=payload.num_questions,
    )


@router.post("/autosave", response_model=AutosaveAnswerResponse)
def handle_autosave_practice(
    payload: AutosaveAnswerRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    return autosave_practice(user_id=current_user.id, payload=payload)


@router.post("/submit", response_model=PracticeSubmitResponse)
def handle_submit_practice(
    payload: PracticeSubmitRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    return submit_practice(
        user_id=current_user.id,
        session_id=payload.session_id,
        answers=payload.answers,
    )