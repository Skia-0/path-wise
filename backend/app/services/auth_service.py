import os
from datetime import datetime, timedelta, timezone

import httpx
from jose import jwt, JWTError
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client

from app.config import get_settings
from app.db.supabase_client import supabase_admin
from app.models.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserProfileResponse,
    SubjectAddedResponse,
)
from app.utils.logger import logger

settings = get_settings()
security = HTTPBearer()

DEFAULT_TIER = "Beginner"


def create_access_token(user_id: str, email: str) -> str:
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _get_auth_client():
    """
    Returns a separate Supabase client used only for password sign-in.
    sign_in_with_password() attaches the user's session to the client it is called on.
    If that were the shared service_role client, every later database query in this
    process would run as the end user, and RLS would block the backend's writes.
    """
    url = os.getenv("SUPABASE_URL", "")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not anon_key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_ANON_KEY is missing from your .env file.")
    return create_client(url, anon_key)


def _rollback_auth_user(user_id: str) -> None:
    """Removes an auth user whose subject setup failed, so the same email can sign up again."""
    try:
        supabase_admin.auth.admin.delete_user(user_id)
        logger.info(f"Rolled back auth user {user_id} after failed subject setup")
    except Exception as e:
        logger.error(f"Could not roll back auth user {user_id}: {str(e)}")


def register_user(payload: UserRegisterRequest) -> TokenResponse:
    # Step 1: create the sign-in account
    try:
        auth_res = supabase_admin.auth.admin.create_user({
            "email": payload.email,
            "password": payload.password,
            "email_confirm": True,
            "user_metadata": {"full_name": payload.full_name}
        })
        user_id = auth_res.user.id
    except Exception as e:
        logger.error(f"User registration failed for {payload.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}"
        )

    # Step 2: create one user_subjects row per chosen subject only
    try:
        for subject in payload.subjects:
            supabase_admin.table("user_subjects").insert({
                "user_id": user_id,
                "subject": subject,
                "current_tier": DEFAULT_TIER,
                "diagnostic_completed": False,
            }).execute()
    except Exception as e:
        logger.error(f"Subject setup failed for {payload.email}: {str(e)}")
        _rollback_auth_user(user_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not set up your subjects. Please try signing up again."
        )

    token = create_access_token(user_id=user_id, email=payload.email)
    logger.info(f"Registered user {payload.email} ({user_id}) with subjects: {', '.join(payload.subjects)}")
    return TokenResponse(access_token=token, user_id=user_id, email=payload.email)


def enrol_subject(user_id: str, subject: str) -> SubjectAddedResponse:
    """Adds a subject to an existing account. Starts at Beginner with no diagnostic done."""
    try:
        existing = (
            supabase_admin.table("user_subjects")
            .select("subject")
            .eq("user_id", user_id)
            .eq("subject", subject)
            .execute()
        )
    except Exception as e:
        logger.error(f"Subject lookup failed for {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not check your subjects right now. Please try again."
        )

    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{subject} is already on your account."
        )

    try:
        supabase_admin.table("user_subjects").insert({
            "user_id": user_id,
            "subject": subject,
            "current_tier": DEFAULT_TIER,
            "diagnostic_completed": False,
        }).execute()
    except Exception as e:
        logger.error(f"Could not add subject {subject} for {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not add the subject right now. Please try again."
        )

    logger.info(f"Added subject {subject} for user {user_id}")
    return SubjectAddedResponse(
        subject=subject,
        current_tier=DEFAULT_TIER,
        diagnostic_completed=False,
    )


def login_user(payload: UserLoginRequest) -> TokenResponse:
    auth_client = _get_auth_client()

    try:
        auth_res = auth_client.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password
        })

        if not auth_res.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        user_id = auth_res.user.id
        token = create_access_token(user_id=user_id, email=payload.email)
        logger.info(f"User logged in successfully: {payload.email}")
        return TokenResponse(access_token=token, user_id=user_id, email=payload.email)

    except HTTPException:
        raise

    except httpx.HTTPError as e:
        # Network problem reaching Supabase Auth (timeouts, connection resets).
        # This is not a wrong password, so do not return 401.
        logger.error(f"Supabase Auth unreachable during login for {payload.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login service is temporarily unreachable. Please try again in a moment."
        )

    except Exception as e:
        logger.warning(f"Failed login attempt for {payload.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserProfileResponse:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        if user_id is None or email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Fast local profile response built from verified JWT payload
    return UserProfileResponse(
        id=user_id,
        email=email,
        full_name=email.split("@")[0].capitalize(),
        created_at=datetime.now(timezone.utc).isoformat()
    )