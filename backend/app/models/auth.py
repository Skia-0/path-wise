import re
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

# The only subjects a student can choose. Must match the names in the questions table.
ALLOWED_SUBJECTS = ("Core Mathematics", "Elective Physics")


def _check_subject(value: str) -> str:
    cleaned = (value or "").strip()
    if cleaned not in ALLOWED_SUBJECTS:
        raise ValueError(f"Subject must be one of: {', '.join(ALLOWED_SUBJECTS)}")
    return cleaned


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    subjects: List[str] = Field(
        ...,
        min_length=1,
        max_length=2,
        description="One or both of: Core Mathematics, Elective Physics",
    )

    @field_validator('email')
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator('password')
    def validate_password(cls, v: str) -> str:
        if len(v.encode('utf-8')) > 72:
            raise ValueError("Password cannot exceed 72 bytes")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v

    @field_validator('subjects')
    def validate_subjects(cls, v: List[str]) -> List[str]:
        cleaned: List[str] = []
        for subject in v:
            checked = _check_subject(subject)
            if checked not in cleaned:
                cleaned.append(checked)
        if not cleaned:
            raise ValueError("Choose at least one subject")
        return cleaned


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator('email')
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class SubjectEnrolRequest(BaseModel):
    subject: str

    @field_validator('subject')
    def validate_subject(cls, v: str) -> str:
        return _check_subject(v)


class SubjectAddedResponse(BaseModel):
    subject: str
    current_tier: str
    diagnostic_completed: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    created_at: str