"""Administrator user-management endpoints."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult

from app.api.deps import AdminUser, DbSession
from app.core.audit import record_event
from app.core.security import hash_password
from app.db.pagination import paginate
from app.models.models import Package, PackageFile, User
from app.schemas.schemas import (
    AdminUserRead,
    BulkQuotaResult,
    BulkQuotaUpdate,
    MessageResponse,
    PasswordReset,
    UserAdminUpdate,
    UserPage,
)
from app.services.quota import user_storage_used
from app.services.storage import storage

router = APIRouter(prefix="/admin/users", tags=["admin"])


def _admin_user_read(user: User, storage_used: int) -> AdminUserRead:
    """Build the admin view of a user with its current storage usage."""
    view = AdminUserRead.model_validate(user)
    view.storage_used = storage_used
    return view


@router.get("", response_model=UserPage)
def list_users(
    db: DbSession,
    admin: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> UserPage:
    """List all registered users, newest first (administrators only)."""
    users, total = paginate(
        db,
        select(User).order_by(User.created_at.desc()),
        limit=limit,
        offset=offset,
    )
    # Aggregate storage usage for just the listed users in one grouped query
    # (avoids a per-user aggregate on paginated listings).
    usage: dict[int, int] = {}
    user_ids = [user.id for user in users]
    if user_ids:
        rows = db.execute(
            select(Package.owner_id, func.coalesce(func.sum(PackageFile.size), 0))
            .select_from(Package)
            .join(PackageFile, PackageFile.package_id == Package.id)
            .where(Package.owner_id.in_(user_ids))
            .group_by(Package.owner_id)
        )
        usage = {owner_id: int(used) for owner_id, used in rows}
    return UserPage(
        items=[_admin_user_read(user, usage.get(user.id, 0)) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/quota", response_model=BulkQuotaResult)
def update_all_quotas(
    payload: BulkQuotaUpdate,
    db: DbSession,
    admin: AdminUser,
    request: Request,
) -> BulkQuotaResult:
    """Set every user's storage quota to the same value (0 = unlimited).

    Overwrites any per-user quotas. It does not change the default applied to
    future accounts, which comes from ``EASYSHARE_STORAGE_QUOTA_PER_USER``.

    Registered before ``/{user_id}`` so the literal ``quota`` segment is not
    captured as a (non-integer) user id.
    """
    result = db.execute(update(User).values(storage_quota=payload.storage_quota))
    db.commit()
    updated = cast("CursorResult[Any]", result).rowcount or 0
    record_event(
        "admin.users.quota.bulk_update",
        request=request,
        actor=f"user:{admin.id}",
        detail={"storage_quota": payload.storage_quota, "count": updated},
    )
    return BulkQuotaResult(updated=updated)


@router.patch("/{user_id}", response_model=AdminUserRead)
def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    db: DbSession,
    admin: AdminUser,
    request: Request,
) -> AdminUserRead:
    """Update a user's profile, active state, admin rights or storage quota.

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
        "admin.user.update",
        request=request,
        actor=f"user:{admin.id}",
        target=f"user:{user.id}",
        detail={key: str(value) for key, value in data.items()},
    )
    return _admin_user_read(user, user_storage_used(db, user.id))


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: int,
    db: DbSession,
    admin: AdminUser,
    request: Request,
) -> MessageResponse:
    """Delete a user and all of their packages, files and shares.

    Administrators cannot delete their own account, so an instance always
    keeps at least one administrator.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    for package in user.packages:
        for file in package.files:
            storage.delete(file.storage_key)

    db.delete(user)
    db.commit()

    record_event(
        "admin.user.delete",
        request=request,
        actor=f"user:{admin.id}",
        target=f"user:{user_id}",
    )
    return MessageResponse(detail="User deleted")


@router.post("/{user_id}/password", response_model=MessageResponse)
def reset_user_password(
    user_id: int,
    payload: PasswordReset,
    db: DbSession,
    admin: AdminUser,
    request: Request,
) -> MessageResponse:
    """Set a new password for a user (administrators only).

    Intended for account recovery. The new password is hashed with Argon2id and
    is never logged or echoed back. For an immediate lockout of a compromised
    account, deactivate it (the account's tokens then stop working at once).
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    record_event(
        "admin.user.password_reset",
        request=request,
        actor=f"user:{admin.id}",
        target=f"user:{user.id}",
    )
    return MessageResponse(detail="Password reset")
