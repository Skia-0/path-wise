from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class SUSSubmission(BaseModel):
    q1: int = Field(..., ge=1, le=5, description="1=Strongly Disagree, 5=Strongly Agree")
    q2: int = Field(..., ge=1, le=5)
    q3: int = Field(..., ge=1, le=5)
    q4: int = Field(..., ge=1, le=5)
    q5: int = Field(..., ge=1, le=5)
    q6: int = Field(..., ge=1, le=5)
    q7: int = Field(..., ge=1, le=5)
    q8: int = Field(..., ge=1, le=5)
    q9: int = Field(..., ge=1, le=5)
    q10: int = Field(..., ge=1, le=5)
    feedback: Optional[str] = ""

class EventLogItem(BaseModel):
    event_type: str = Field(..., min_length=2, max_length=100)
    metadata: Optional[Dict[str, Any]] = None