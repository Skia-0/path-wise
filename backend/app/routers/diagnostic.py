from fastapi import APIRouter, Depends
from app.models.auth import UserProfileResponse
from app.services.auth_service import get_current_user
from app.models.diagnostic import (
    DiagnosticStartRequest,
    DiagnosticStartResponse,
    DiagnosticSubmitRequest,
    DiagnosticSubmitResponse,
)
from app.models.practice import AutosaveAnswerRequest, AutosaveAnswerResponse
from app.services.adaptive_engine import start_diagnostic, submit_diagnostic, autosave_answer

router = APIRouter(prefix="/api/v1/diagnostic", tags=["Adaptive Diagnostic Engine"])


@router.post("/start", response_model=DiagnosticStartResponse)
def handle_start_diagnostic(
    payload: DiagnosticStartRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    return start_diagnostic(user_id=current_user.id, subject=payload.subject)


@router.post("/autosave", response_model=AutosaveAnswerResponse)
def handle_autosave(
    payload: AutosaveAnswerRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    return autosave_answer(user_id=current_user.id, payload=payload)


@router.post("/submit", response_model=DiagnosticSubmitResponse)
def handle_submit_diagnostic(
    payload: DiagnosticSubmitRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    return submit_diagnostic(
        user_id=current_user.id,
        attempt_id=payload.attempt_id,
        answers=payload.answers,
    )