from pydantic import BaseModel
from typing import List, Optional


class DiagnosticStartRequest(BaseModel):
    subject: str  # "Core Mathematics" or "Elective Physics"


class QuestionOption(BaseModel):
    label: str  # "A", "B", "C", "D", "E"
    text: str


class DiagnosticQuestionResponse(BaseModel):
    id: str
    question_number: int
    question_text: str
    options: List[QuestionOption]
    diagram_url: Optional[str] = None
    topic_code: str
    topic_name: str


class AnswerSubmission(BaseModel):
    question_id: str
    selected_option: str  # "A", "B", "C", "D", or "E"


class DiagnosticStartResponse(BaseModel):
    attempt_id: str
    subject: str
    total_questions: int
    expires_at: str
    questions: List[DiagnosticQuestionResponse]
    saved_answers: List[AnswerSubmission] = []  # choices already saved for a resumed attempt


class DiagnosticSubmitRequest(BaseModel):
    attempt_id: str
    answers: List[AnswerSubmission]


class TopicBreakdown(BaseModel):
    topic_code: str
    topic_name: str
    correct_count: int
    total_count: int
    percentage: float


class DiagnosticSubmitResponse(BaseModel):
    attempt_id: str
    subject: str
    score: float
    assigned_tier: str
    waec_grade: str
    completed_at: str
    topic_breakdown: List[TopicBreakdown]