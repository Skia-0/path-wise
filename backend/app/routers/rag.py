from fastapi import APIRouter, Depends, HTTPException, status
from app.models.rag import (
    Paper2EvalRequest,
    Paper2EvalResponse,
    TopicNoteSummaryRequest,
    TopicNoteSummaryResponse,
)
from app.services.rag_evaluator import evaluate_paper2_answer, generate_summary_notes
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/v1/rag", tags=["Paper 2 RAG & AI Tutor"])


@router.post("/eval-paper2", response_model=Paper2EvalResponse)
def evaluate_paper2_endpoint(
    request: Paper2EvalRequest,
    current_user: dict = Depends(get_current_user),
):
    """Evaluates a student's Paper 2 written answer against the official WAEC marking scheme."""
    try:
        return evaluate_paper2_answer(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate Paper 2 answer: {str(e)}",
        )


@router.post("/summarize-notes", response_model=TopicNoteSummaryResponse)
def summarize_notes_endpoint(
    request: TopicNoteSummaryRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generates structured AI study revision notes for a topic & subject."""
    try:
        return generate_summary_notes(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate study notes: {str(e)}",
        )