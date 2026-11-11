from fastapi import APIRouter, Request, Depends
from app.utils.rate_limiter import limiter
from app.models.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserProfileResponse,
    SubjectEnrolRequest,
    SubjectAddedResponse,
)
from app.services.auth_service import (
    register_user,
    login_user,
    get_current_user,
    enrol_subject,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/signup", response_model=TokenResponse)
def signup(payload: UserRegisterRequest):
    return register_user(payload)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/15minutes")
def login(request: Request, payload: UserLoginRequest):
    return login_user(payload)


@router.get("/me", response_model=UserProfileResponse)
def get_profile(current_user: UserProfileResponse = Depends(get_current_user)):
    return current_user


@router.post("/subjects", response_model=SubjectAddedResponse, status_code=201)
def add_subject(
    payload: SubjectEnrolRequest,
    current_user: UserProfileResponse = Depends(get_current_user),
):
    """Adds the second subject to an existing account. Returns 409 if it is already there."""
    return enrol_subject(current_user.id, payload.subject)