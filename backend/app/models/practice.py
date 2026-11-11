from pydantic import BaseModel, Field
from typing import List, Optional
from app.models.diagnostic import DiagnosticQuestionResponse, QuestionOption, AnswerSubmission, TopicBreakdown


class PracticeStartRequest(BaseModel):
    subject: str  # "Core Mathematics" or "Elective Physics"
    num_questions: int = Field(default=20, ge=20, le=50)  # Minimum 20 enforced


class PracticeStartResponse(BaseModel):
    session_id: str
    subject: str
    target_tier: str
    total_questions: int
    questions: List[DiagnosticQuestionResponse]
    saved_answers: List[AnswerSubmission] = []  # restores choices when resuming


class AutosaveAnswerRequest(BaseModel):
    attempt_id: str
    session_type: str  # "diagnostic" or "practice"
    question_id: str
    selected_option: str  # "A", "B", "C", "D", or "E"


class AutosaveAnswerResponse(BaseModel):
    status: str = "saved"
    question_id: str
    selected_option: str


class PracticeSubmitRequest(BaseModel):
    session_id: str
    answers: List[AnswerSubmission]


class QuestionReviewItem(BaseModel):
    question_id: str
    question_text: str
    topic_name: str
    diagram_url: Optional[str] = None
    selected_option: Optional[str] = None  # Choice made by student ('A'-'E')
    correct_option: str  # Correct option letter for this student's shuffled view
    is_correct: bool
    explanation: Optional[str] = None  # WAEC step-by-step working / explanation
    options: List[QuestionOption]


class PracticeSubmitResponse(BaseModel):
    session_id: str
    subject: str
    score: float
    target_tier: str
    new_tier: str
    waec_grade: str
    completed_at: str
    topic_breakdown: List[TopicBreakdown]
    question_reviews: List[QuestionReviewItem] = []