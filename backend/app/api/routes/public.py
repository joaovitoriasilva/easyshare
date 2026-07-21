"""Public share access routes used by recipients (no authentication)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession
from app.core.audit import enqueue_event, record_event
from app.core.config import settings
from app.core.rate_limit import DOWNLOAD, EXPENSIVE, SENSITIVE, limiter
from app.core.security import (
    create_share_access_token,
    decode_share_access_token,
    generate_verification_code,
    hash_verification_code,
    verify_verification_code,
)
from app.core.utils import as_utc, normalize_email
from app.models.models import (
    Package,
    PackageFile,
    Share,
    ShareAccessCode,
    ShareVisibility,
)
from app.schemas.schemas import (
    PublicFile,
    PublicShareRead,
    ShareAccessRequest,
    ShareVerifyRequest,
)
from app.services.archive import build_archive_download, validate_archive_request
from app.services.counters import counter_buffer
from app.services.email import send_share_verification_code
from app.services.storage import storage

router = APIRouter(prefix="/s", tags=["public"])


def _get_active_share(db: DbSession, token: str) -> Share:
    # Eager-load the package, its files and the allow-list up front so the hot
    # public view/download paths don't fan out into several lazy follow-up
    # queries while building the response.
    share = db.scalar(
        select(Share)
        .where(Share.token == token)
        .options(
            selectinload(Share.package).selectinload(Package.files),
            selectinload(Share.allowed_emails),
        )
    )
    if share is None or not share.is_enabled or _is_expired(share):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Share not found"
        )
    return share


def _is_expired(share: Share) -> bool:
    """Return whether a share has passed its optional expiry time."""
    if share.expires_at is None:
        return False
    return as_utc(share.expires_at) <= datetime.now(UTC)


def _email_allowed(share: Share, email: str) -> bool:
    """Return whether ``email`` is on a restricted share's allow-list."""
    allowed = {entry.email for entry in share.allowed_emails}
    return normalize_email(email) in allowed


def _authorize_email(share: Share, email: str | None) -> None:
    """Ensure ``email`` may access a restricted share; no-op for public shares."""
    if share.visibility == ShareVisibility.PUBLIC:
        return
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This share requires a valid email address",
        )
    if not _email_allowed(share, email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This email is not allowed to access the share",
        )


def _authorize_download(share: Share, access_token: str | None) -> str | None:
    """Authorize a download request, returning the authorised email (if any).

    Public shares are always downloadable (returns ``None``). Restricted shares
    require the opaque, short-lived token issued by :func:`access_share`; the
    email it certifies is re-checked against the current allow-list so access
    can be revoked by removing the address.
    """
    if share.visibility == ShareVisibility.PUBLIC:
        return None
    email = (
        decode_share_access_token(access_token, share.token)
        if access_token
        else None
    )
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This share requires a valid access token",
        )
    if not _email_allowed(share, email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This email is not allowed to access the share",
        )
    return email


def _files_payload(share: Share) -> list[PublicFile]:
    return [
        PublicFile(
            id=f.id,
            filename=f.filename,
            content_type=f.content_type,
            size=f.size,
        )
        for f in share.package.files
    ]


def _public_share_read(
    share: Share,
    *,
    reveal_files: bool,
    download_token: str | None = None,
    verification_required: bool = False,
) -> PublicShareRead:
    """Build the public view of a share, optionally revealing its file list."""
    return PublicShareRead(
        token=share.token,
        package_name=share.package.name,
        package_description=share.package.description,
        visibility=share.visibility,
        requires_email=share.visibility == ShareVisibility.RESTRICTED,
        files=_files_payload(share) if reveal_files else [],
        download_token=download_token,
        verification_required=verification_required,
    )


@router.get("/{token}", response_model=PublicShareRead)
@limiter.limit(DOWNLOAD)
def view_share(token: str, db: DbSession, request: Request) -> PublicShareRead:
    """View share metadata. Files are hidden for restricted shares.

    Each view bumps a denormalised counter on the share rather than writing an
    audit row, so a heavily crawled or refreshed public link cannot amplify into
    unbounded audit-table writes. The increment is buffered in process memory
    and flushed in coalesced batches by a background task, so a viral link does
    not serialise a per-hit ``UPDATE`` + commit on the single share row. The
    endpoint is also rate-limited.
    """
    share = _get_active_share(db, token)
    response = _public_share_read(
        share, reveal_files=share.visibility != ShareVisibility.RESTRICTED
    )
    counter_buffer.add_view(share.id)
    return response


def _email_verification_required(share: Share) -> bool:
    """Whether unlocking this share needs an emailed one-time code."""
    return (
        settings.email_verification_enabled
        and share.visibility == ShareVisibility.RESTRICTED
    )


def _issue_verification_code(
    db: DbSession, share: Share, email: str, background_tasks: BackgroundTasks
) -> None:
    """Generate, persist (replacing any prior) and email a one-time code.

    The code is committed before the email is scheduled so a delivery failure
    never loses it; the send itself is handed to a background task so the
    (possibly slow) SMTP round-trip runs after the response is returned rather
    than holding a worker thread while the client waits. The plaintext is
    emailed but only its keyed hash is stored.
    """
    normalized = normalize_email(email)
    code = generate_verification_code()
    code_hash = hash_verification_code(share.id, normalized, code)
    expires = datetime.now(UTC) + timedelta(
        minutes=settings.share_verification_code_ttl_minutes
    )
    # Read the package name before the commit below expires the ORM instance.
    package_name = share.package.name
    existing = db.scalar(
        select(ShareAccessCode).where(
            ShareAccessCode.share_id == share.id,
            ShareAccessCode.email == normalized,
        )
    )
    if existing is not None:
        existing.code_hash = code_hash
        existing.attempts = 0
        existing.expires_at = expires
    else:
        db.add(
            ShareAccessCode(
                share_id=share.id,
                email=normalized,
                code_hash=code_hash,
                expires_at=expires,
            )
        )
    db.commit()
    # Deliver the code after the response is sent so the (possibly slow) SMTP
    # round-trip never occupies a worker thread while the client waits.
    background_tasks.add_task(
        send_share_verification_code, normalized, code, package_name=package_name
    )


def _consume_verification_code(
    db: DbSession, share: Share, email: str, code: str
) -> bool:
    """Validate a submitted code, enforcing expiry and an attempt cap.

    A correct code is single-use (deleted on success). Expired codes and codes
    that exhaust the attempt budget are discarded so they cannot be retried.
    """
    normalized = normalize_email(email)
    record = db.scalar(
        select(ShareAccessCode).where(
            ShareAccessCode.share_id == share.id,
            ShareAccessCode.email == normalized,
        )
    )
    if record is None:
        return False
    if as_utc(record.expires_at) <= datetime.now(UTC) or (
        record.attempts >= settings.share_verification_max_attempts
    ):
        db.delete(record)
        db.commit()
        return False
    if verify_verification_code(share.id, normalized, code, record.code_hash):
        db.delete(record)
        db.commit()
        return True
    record.attempts += 1
    db.commit()
    return False


@router.post("/{token}/access", response_model=PublicShareRead)
@limiter.limit(SENSITIVE)
def access_share(
    request: Request,
    token: str,
    payload: ShareAccessRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
) -> PublicShareRead:
    """Unlock a restricted share by providing an allowed email address.

    When email verification is enabled, this only *starts* the flow: a one-time
    code is emailed and the response asks the recipient to confirm it via
    ``/verify`` (files stay hidden). To avoid revealing whether an address is
    allow-listed, the response is identical whether or not the email is allowed;
    a code is only actually sent to an allow-listed address. When email is not
    configured the historical behaviour applies: knowing an allowed email grants
    access immediately.
    """
    share = _get_active_share(db, token)
    email = str(payload.email)

    if _email_verification_required(share):
        if _email_allowed(share, email):
            _issue_verification_code(db, share, email, background_tasks)
            record_event(
                "share.access.code_sent",
                request=request,
                actor=email,
                target=f"share:{token[:8]}",
                package_id=share.package_id,
            )
        else:
            record_event(
                "share.access.denied",
                request=request,
                actor=email,
                target=f"share:{token[:8]}",
                package_id=share.package_id,
                detail={"reason": "not_allowed"},
            )
        # Uniform response regardless of allow-list membership.
        return _public_share_read(
            share, reveal_files=False, verification_required=True
        )

    try:
        _authorize_email(share, email)
    except HTTPException as exc:
        record_event(
            "share.access.denied",
            request=request,
            actor=email,
            target=f"share:{token[:8]}",
            package_id=share.package_id,
            detail={"status": exc.status_code},
        )
        raise
    record_event(
        "share.access.granted",
        request=request,
        actor=email,
        target=f"share:{token[:8]}",
        package_id=share.package_id,
    )
    download_token = (
        create_share_access_token(share.token, normalize_email(email))
        if share.visibility == ShareVisibility.RESTRICTED
        else None
    )
    return _public_share_read(share, reveal_files=True, download_token=download_token)


@router.post("/{token}/verify", response_model=PublicShareRead)
@limiter.limit(SENSITIVE)
def verify_share(
    request: Request, token: str, payload: ShareVerifyRequest, db: DbSession
) -> PublicShareRead:
    """Confirm the emailed one-time code and unlock a restricted share.

    The email must still be on the allow-list (so removing an address revokes a
    pending code) and the code must be correct, unexpired and within the attempt
    budget. Success returns the same short-lived download token as the
    no-verification path.
    """
    share = _get_active_share(db, token)
    email = str(payload.email)
    if not _email_verification_required(share):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification is not required for this share",
        )
    authorized = _email_allowed(share, email) and _consume_verification_code(
        db, share, email, payload.code
    )
    if not authorized:
        record_event(
            "share.verify.denied",
            request=request,
            actor=email,
            target=f"share:{token[:8]}",
            package_id=share.package_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired verification code",
        )
    record_event(
        "share.access.granted",
        request=request,
        actor=email,
        target=f"share:{token[:8]}",
        package_id=share.package_id,
        detail={"via": "code"},
    )
    download_token = create_share_access_token(share.token, normalize_email(email))
    return _public_share_read(share, reveal_files=True, download_token=download_token)


def _resolve_file(share: Share, file_id: int) -> PackageFile:
    for file in share.package.files:
        if file.id == file_id:
            return file
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
    )


def _authorize_download_or_deny(
    share: Share,
    access: str | None,
    request: Request,
    *,
    denied_detail: dict[str, Any] | None = None,
) -> str | None:
    """Authorize a download, auditing a denial before re-raising on failure."""
    try:
        return _authorize_download(share, access)
    except HTTPException as exc:
        detail: dict[str, Any] = {"status": exc.status_code}
        if denied_detail:
            detail.update(denied_detail)
        record_event(
            "share.download.denied",
            request=request,
            target=f"share:{share.token[:8]}",
            package_id=share.package_id,
            detail=detail,
        )
        raise


@router.get("/{token}/files/{file_id}/download")
@limiter.limit(DOWNLOAD)
def download_shared_file(
    token: str,
    file_id: int,
    db: DbSession,
    request: Request,
    access: str | None = Query(default=None),
) -> Response:
    """Download a single file from a share."""
    share = _get_active_share(db, token)
    email = _authorize_download_or_deny(
        share, access, request, denied_detail={"file_id": file_id}
    )
    record = _resolve_file(share, file_id)
    filename = record.filename
    storage_key = record.storage_key
    content_type = record.content_type
    package_id = share.package_id
    # Buffer the download count in memory (flushed in coalesced batches) instead
    # of an UPDATE + commit on the file row per hit.
    counter_buffer.add_downloads([record.id])
    # Audit the download attempt now — before the file streams — but hand the row
    # to the in-memory audit buffer so a viral link never pays an INSERT + commit
    # on the request's critical path. The attempt's timestamp, actor and request
    # id are captured here; the row is persisted in a coalesced batch.
    enqueue_event(
        "share.download",
        request=request,
        actor=email,
        target=f"share:{token[:8]}",
        package_id=package_id,
        detail={"file_id": file_id, "filename": filename},
    )
    return storage.download_response(
        storage_key, filename=filename, content_type=content_type
    )


@router.get("/{token}/download")
@limiter.limit(EXPENSIVE)
def download_shared_archive(
    token: str,
    db: DbSession,
    request: Request,
    access: str | None = Query(default=None),
    file_ids: list[int] | None = Query(default=None),
) -> StreamingResponse:
    """Download all files, or a selected subset, as a zip archive.

    Recipients may pass ``file_ids`` repeatedly to select specific files;
    when omitted, every file in the package is included. The archive is streamed
    incrementally, so it is never buffered in full, and the per-file download
    count is bumped only once the archive has finished streaming (a client that
    disconnects part-way is not counted).
    """
    share = _get_active_share(db, token)
    email = _authorize_download_or_deny(share, access, request)

    if file_ids:
        selected = [f for f in share.package.files if f.id in set(file_ids)]
    else:
        selected = list(share.package.files)

    validate_archive_request(
        selected, empty_detail="No matching files to download"
    )

    # Snapshot ids while the ORM instances are fresh; the download is counted by
    # the archive builder's on-complete hook once the stream actually finishes.
    selected_ids = [file.id for file in selected]
    package_id = share.package_id
    response = build_archive_download(
        selected,
        package_name=share.package.name,
        on_complete=lambda: counter_buffer.add_downloads(selected_ids),
    )
    # Audit the attempt now (before streaming) via the non-blocking audit buffer.
    # The counter above still only counts a completed archive; auditing the
    # attempt records who requested it even if the client disconnects mid-stream.
    enqueue_event(
        "share.download",
        request=request,
        actor=email,
        target=f"share:{token[:8]}",
        package_id=package_id,
        detail={"file_ids": selected_ids, "archive": True},
    )
    return response
