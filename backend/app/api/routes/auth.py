"""Authentication routes: registration, login and current user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession
from app.core.audit import record_event
from app.core.config import settings
from app.core.rate_limit import SENSITIVE, limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import User
from app.schemas.schemas import AuthConfig, Token, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    """Public auth-related feature flags for the frontend."""
    return AuthConfig(allow_registration=settings.allow_registration)


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
    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    record_event(db, "user.register", request=request, actor=f"user:{user.id}")
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
        record_event(db, "login.failure", request=request, actor=identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        record_event(db, "login.blocked", request=request, actor=f"user:{user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive"
        )
    token = create_access_token(user.id)
    record_event(db, "login.success", request=request, actor=f"user:{user.id}")
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
def read_me(current_user: CurrentUser) -> User:
    """Return the currently authenticated user."""
    return current_user
