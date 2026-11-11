from typing import List, Optional
from pydantic import BaseModel, Field


class Paper2EvalRequest(BaseModel):
    sub_question_id: str = Field(..., description="UUID of the Paper 2 sub-question")
    student_answer: str = Field(..., min_length=1, description="Student's written solution")


class Paper2EvalResponse(BaseModel):
    sub_question_id: str
    earned_marks: float
    max_marks: float
    percentage: float
    waec_grade: str
    feedback: str
    step_breakdown: List[str]
    key_concepts_missed: List[str]
    is_ai_evaluated: bool = True


class TopicNoteSummaryRequest(BaseModel):
    topic_code: str = Field(..., description="Canonical topic code or name (e.g. C-MATH-ALG-01 or Algebra)")
    subject: str = Field(..., description="Subject name (Core Mathematics or Elective Physics)")


class TopicNoteSummaryResponse(BaseModel):
    topic_name: str
    subject: str
    key_definitions: List[str]
    essential_formulas: List[str]
    common_waec_traps: List[str]
    step_by_step_exam_tips: List[str]
    summary_text: str
    is_ai_generated: bool = True