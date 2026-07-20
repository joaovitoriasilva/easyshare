"""Resumable, chunked upload endpoints for large files.

A client opens a session (declaring the filename and total size), then PATCHes
consecutive byte ranges. The server appends each chunk to a scratch file and
tracks the authoritative received offset, so a dropped connection or a page
reload resumes from the last acknowledged byte instead of restarting. When the
received offset reaches the declared size the scratch file is streamed into the
real storage backend and a ``PackageFile`` row is created.

Every endpoint is scoped to a package the caller owns (via ``OwnedPackage``) and
to a session belonging to that package, so one user can never touch another's
in-progress upload.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request, Response, status
from sqlalchemy import delete, select

from app.api.deps import DbSession, OwnedPackage
from app.core.config import settings
from app.models.models import PackageFile, UploadSession
from app.schemas.schemas import (
    PackageFileRead,
    UploadSessionCreate,
    UploadSessionRead,
)
from app.services import chunked
from app.services.files import store_package_file
from app.services.quota import remaining_upload_cap
from app.services.storage import FileTooLargeError
from app.services.validation import sanitize_upload_filename

router = APIRouter(prefix="/packages/{package_id}/uploads", tags=["uploads"])


def _session_read(session: UploadSession, *, file: PackageFile | None = None) -> UploadSessionRead:
    """Shape the client-facing view of an upload session's current state."""
    return UploadSessionRead(
        upload_id=session.token,
        offset=session.received,
        size=session.total_size,
        filename=session.filename,
        chunk_size=settings.chunk_size,
        complete=file is not None,
        file=PackageFileRead.model_validate(file) if file is not None else None,
    )


def _get_session(db: DbSession, package_id: int, upload_id: str) -> UploadSession:
    """Fetch a session belonging to ``package_id`` or raise 404."""
    session = db.scalar(
        select(UploadSession).where(
            UploadSession.token == upload_id,
            UploadSession.package_id == package_id,
        )
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found"
        )
    return session


@router.post("", response_model=UploadSessionRead, status_code=status.HTTP_201_CREATED)
def create_upload(
    payload: UploadSessionCreate, package: OwnedPackage, db: DbSession
) -> UploadSessionRead:
    """Open a resumable upload, validating the declared size against the caps."""
    if len(package.files) >= settings.max_files_per_package:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum number of files per package reached",
        )
    safe_filename = sanitize_upload_filename(payload.filename)
    cap, cap_message = remaining_upload_cap(db, package)
    if cap <= 0 or payload.size > cap:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=cap_message
        )
    session = UploadSession(
        token=secrets.token_urlsafe(24),
        package_id=package.id,
        filename=safe_filename,
        content_type=payload.content_type or "application/octet-stream",
        total_size=payload.size,
        received=0,
        scratch_key=chunked.create_scratch(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_read(session)


@router.get("/{upload_id}", response_model=UploadSessionRead)
def get_upload(
    upload_id: str, package: OwnedPackage, db: DbSession
) -> UploadSessionRead:
    """Return the current offset so a client can resume an interrupted upload.

    Reconciles ``received`` with the scratch file's actual length in case a
    crash lost the last offset update, so the client is never told to resume
    past what is truly on disk.
    """
    session = _get_session(db, package.id, upload_id)
    actual = chunked.scratch_size(session.scratch_key)
    if actual != session.received:
        session.received = actual
        db.commit()
    return _session_read(session)


def _finalize(db: DbSession, package: OwnedPackage, session: UploadSession) -> PackageFile:
    """Move a completed scratch file into storage and create its package file."""
    token = session.token
    cap, cap_message = remaining_upload_cap(db, package)
    if cap <= 0 or session.total_size > cap:
        chunked.discard(session.scratch_key)
        db.delete(session)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=cap_message
        )
    try:
        record = store_package_file(
            db,
            package,
            filename=session.filename,
            content_type=session.content_type,
            writer=lambda key: chunked.finalize(
                session.scratch_key, key, max_bytes=cap
            ),
        )
    except FileTooLargeError as exc:
        db.rollback()
        # The record insert is undone by the rollback; remove the now-orphaned
        # session row with a direct statement (the ORM object is expired).
        db.execute(delete(UploadSession).where(UploadSession.token == token))
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=cap_message
        ) from exc
    db.delete(session)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/{upload_id}", response_model=UploadSessionRead)
def upload_chunk(
    upload_id: str,
    package: OwnedPackage,
    db: DbSession,
    request: Request,
    response: Response,
    chunk: Annotated[bytes, Body(media_type="application/offset+octet-stream")] = b"",
) -> UploadSessionRead:
    """Append one chunk at ``Upload-Offset``; finalize when the file is complete.

    The offset must equal the session's current received length (so a retried or
    out-of-order chunk cannot corrupt the file), and the chunk must not push the
    total past the declared size. On the final chunk the assembled file is moved
    into storage and its ``PackageFile`` is returned with ``complete: true``.
    """
    session = _get_session(db, package.id, upload_id)
    try:
        offset = int(request.headers["upload-offset"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or invalid Upload-Offset header",
        ) from exc
    if len(chunk) > settings.max_chunk_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Chunk too large"
        )
    if offset != session.received:
        # Tell the client where to resume instead of accepting a bad write. The
        # header must go on the exception itself: a header set on the injected
        # Response is dropped once an HTTPException is raised.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chunk offset does not match the expected position",
            headers={"Upload-Offset": str(session.received)},
        )
    if offset + len(chunk) > session.total_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chunk exceeds the declared file size",
        )
    try:
        received = chunked.append_chunk(session.scratch_key, offset, chunk)
    except chunked.ChunkOffsetError as exc:
        # Scratch and DB disagreed (e.g. after a crash): reconcile and report.
        session.received = chunked.scratch_size(session.scratch_key)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chunk offset does not match the expected position",
            headers={"Upload-Offset": str(session.received)},
        ) from exc
    session.received = received
    db.commit()

    if received >= session.total_size:
        record = _finalize(db, package, session)
        response.headers["Upload-Offset"] = str(record.size)
        return _session_read_complete(record, session.filename)
    response.headers["Upload-Offset"] = str(received)
    return _session_read(session)


def _session_read_complete(record: PackageFile, filename: str) -> UploadSessionRead:
    """Shape the completion response once the session row itself is gone."""
    return UploadSessionRead(
        upload_id="",
        offset=record.size,
        size=record.size,
        filename=filename,
        chunk_size=settings.chunk_size,
        complete=True,
        file=PackageFileRead.model_validate(record),
    )


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def abort_upload(
    upload_id: str, package: OwnedPackage, db: DbSession
) -> Response:
    """Abort an in-progress upload, discarding its scratch file."""
    session = _get_session(db, package.id, upload_id)
    chunked.discard(session.scratch_key)
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
