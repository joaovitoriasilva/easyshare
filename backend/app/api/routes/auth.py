"""Authentication routes: registration, login and current user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.core.audit import record_event
from app.core.config import settings
from app.core.rate_limit import SENSITIVE, limiter
from app.core.security import (
    create_access_token,
    dummy_verify,
    hash_password,
    verify_password,
)
from app.models.models import User
from app.schemas.schemas import (
    AuthConfig,
    MessageResponse,
    PasswordChange,
    StorageUsage,
    Token,
    UserCreate,
    UserRead,
)
from app.services.quota import user_storage_used

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    """Public auth-related feature flags for the frontend."""
    return AuthConfig(
        allow_registration=settings.allow_registration,
        max_file_size=settings.max_file_size,
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit(SENSITIVE)
def register(request: Request, payload: UserCreate, db: DbSession) -> User:
    """Register a new user account."""
    if not settings.allow_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled",
        )
    existing = db.scalar(
        select(User).where(
            or_(User.email == payload.email, User.username == payload.username)
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with that email or username already exists",
        )
    # The very first account created on a fresh instance becomes an admin, so an
    # administrator always exists without any out-of-band configuration.
    is_first_user = db.scalar(select(func.count()).select_from(User)) == 0
    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
        is_admin=is_first_user,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    record_event(
        "user.register",
        request=request,
        actor=f"user:{user.id}",
        detail={"is_admin": user.is_admin},
    )
    return user


@router.post("/login", response_model=Token)
@limiter.limit(SENSITIVE)
def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> Token:
    """Authenticate with username/email and password, returning a JWT."""
    identifier = form_data.username
    user = db.scalar(
        select(User).where(
            or_(User.email == identifier, User.username == identifier)
        )
    )
    if user is None or not verify_password(form_data.password, user.hashed_password):
        # Equalise timing for unknown usernames so accounts can't be enumerated
        # by measuring how long a failed login takes.
        if user is None:
            dummy_verify()
        record_event("login.failure", request=request, actor=identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        record_event("login.blocked", request=request, actor=f"user:{user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive"
        )
    token = create_access_token(user.id)
    record_event("login.success", request=request, actor=f"user:{user.id}")
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
def read_me(current_user: CurrentUser) -> User:
    """Return the currently authenticated user."""
    return current_user


@router.get("/me/usage", response_model=StorageUsage)
def read_my_usage(current_user: CurrentUser, db: DbSession) -> StorageUsage:
    """Return the signed-in user's storage consumption and quota.

    Kept separate from ``/auth/me`` (which the SPA polls on every navigation)
    so the usage aggregate is only computed on the screens that display it.
    """
    return StorageUsage(
        storage_used=user_storage_used(db, current_user.id),
        storage_quota=current_user.storage_quota,
    )


@router.post("/me/password", response_model=MessageResponse)
@limiter.limit(SENSITIVE)
def change_my_password(
    request: Request,
    payload: PasswordChange,
    db: DbSession,
    current_user: CurrentUser,
) -> MessageResponse:
    """Change the authenticated user's password.

    The current password must be supplied and verified before the change is
    applied, so an unattended, already-authenticated session cannot silently
    set a new password. Access tokens are stateless and remain valid until they
    expire; deactivating an account is the tool for an immediate lockout.
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        record_event(
            "user.password.change_failed",
            request=request,
            actor=f"user:{current_user.id}",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    record_event(
        "user.password.change", request=request, actor=f"user:{current_user.id}"
    )
    return MessageResponse(detail="Password updated")
