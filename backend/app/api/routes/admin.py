"""Administrator user-management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select

from app.api.deps import AdminUser, DbSession
from app.core.audit import record_event
from app.models.models import User
from app.schemas.schemas import UserAdminUpdate, UserPage, UserRead

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=UserPage)
def list_users(
    db: DbSession,
    admin: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> UserPage:
    """List all registered users, newest first (administrators only)."""
    total = db.scalar(select(func.count()).select_from(User)) or 0
    users = db.scalars(
        select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    )
    return UserPage(
        items=[UserRead.model_validate(user) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    db: DbSession,
    admin: AdminUser,
    request: Request,
) -> User:
    """Update a user's profile, active state or admin rights.

    Administrators cannot revoke their own admin rights or deactivate their own
    account, so an instance always keeps at least one active administrator.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.id == admin.id and payload.is_admin is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin rights",
        )
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    data = payload.model_dump(exclude_unset=True)

    if "email" in data or "username" in data:
        clash = db.scalar(
            select(User).where(
                User.id != user.id,
                or_(
                    User.email == data.get("email", user.email),
                    User.username == data.get("username", user.username),
                ),
            )
        )
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another user already uses that email or username",
            )

    for field, value in data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)

    record_event(
        db,
        "admin.user.update",
        request=request,
        actor=f"user:{admin.id}",
        target=f"user:{user.id}",
        detail={key: str(value) for key, value in data.items()},
    )
    return user
