"""Tests for resumable, chunked uploads."""

from __future__ import annotations

from datetime import datetime

from app.core.config import settings
from app.models.models import UploadSession
from app.services import chunked
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from tests.conftest import register_and_login

_OCTET = "application/offset+octet-stream"


def _create_package(client: TestClient, headers: dict[str, str]) -> int:
    return client.post(
        "/api/packages", json={"name": "Pkg", "description": None}, headers=headers
    ).json()["id"]


def _open_session(
    client: TestClient, pkg_id: int, headers: dict[str, str], *, filename: str, size: int
) -> dict[str, object]:
    resp = client.post(
        f"/api/packages/{pkg_id}/uploads",
        json={"filename": filename, "size": size},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _send_chunk(
    client: TestClient,
    pkg_id: int,
    upload_id: str,
    headers: dict[str, str],
    *,
    offset: int,
    data: bytes,
):
    return client.patch(
        f"/api/packages/{pkg_id}/uploads/{upload_id}",
        content=data,
        headers={**headers, "Upload-Offset": str(offset), "Content-Type": _OCTET},
    )


def test_chunked_upload_end_to_end(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    payload = b"0123456789" * 30  # 300 bytes
    session = _open_session(
        client, pkg_id, headers, filename="big.txt", size=len(payload)
    )
    upload_id = session["upload_id"]
    assert session["offset"] == 0
    assert session["complete"] is False

    # Send in three 100-byte chunks.
    file_id: int | None = None
    for start in range(0, len(payload), 100):
        chunk = payload[start : start + 100]
        resp = _send_chunk(
            client, pkg_id, upload_id, headers, offset=start, data=chunk
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if start + len(chunk) >= len(payload):
            assert body["complete"] is True
            file_id = body["file"]["id"]
            assert body["file"]["filename"] == "big.txt"
            assert body["file"]["size"] == len(payload)
        else:
            assert body["complete"] is False
            assert body["offset"] == start + len(chunk)

    assert file_id is not None
    # The file is now part of the package...
    pkg = client.get(f"/api/packages/{pkg_id}", headers=headers).json()
    assert [f["id"] for f in pkg["files"]] == [file_id]
    # ...and its bytes round-trip exactly.
    token = client.post(
        f"/api/packages/{pkg_id}/download-token", headers=headers
    ).json()["token"]
    downloaded = client.get(
        f"/api/packages/{pkg_id}/files/{file_id}/download?token={token}"
    )
    assert downloaded.content == payload

    # The session row is gone once finalized.
    status = client.get(
        f"/api/packages/{pkg_id}/uploads/{upload_id}", headers=headers
    )
    assert status.status_code == 404


def test_chunked_upload_resume_reports_offset(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    payload = b"abcdefghij" * 20  # 200 bytes
    session = _open_session(
        client, pkg_id, headers, filename="resume.txt", size=len(payload)
    )
    upload_id = session["upload_id"]

    # Upload only the first half, then "reconnect" and ask where to resume.
    _send_chunk(client, pkg_id, upload_id, headers, offset=0, data=payload[:100])
    status = client.get(
        f"/api/packages/{pkg_id}/uploads/{upload_id}", headers=headers
    ).json()
    assert status["offset"] == 100
    assert status["complete"] is False

    # Finish from the reported offset.
    resp = _send_chunk(
        client, pkg_id, upload_id, headers, offset=100, data=payload[100:]
    )
    assert resp.status_code == 200
    assert resp.json()["complete"] is True


def test_chunk_offset_mismatch_returns_409_with_offset(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    session = _open_session(client, pkg_id, headers, filename="x.txt", size=100)
    upload_id = session["upload_id"]

    _send_chunk(client, pkg_id, upload_id, headers, offset=0, data=b"a" * 40)
    # Wrong offset (should be 40): rejected, and told where to resume.
    resp = _send_chunk(
        client, pkg_id, upload_id, headers, offset=0, data=b"b" * 10
    )
    assert resp.status_code == 409
    assert resp.headers["Upload-Offset"] == "40"


def test_chunk_exceeding_declared_size_rejected(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    session = _open_session(client, pkg_id, headers, filename="x.txt", size=50)
    upload_id = session["upload_id"]
    resp = _send_chunk(
        client, pkg_id, upload_id, headers, offset=0, data=b"z" * 80
    )
    assert resp.status_code == 400


def test_open_session_rejects_oversized_declaration(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    resp = client.post(
        f"/api/packages/{pkg_id}/uploads",
        json={"filename": "big.txt", "size": settings.max_file_size + 1},
        headers=headers,
    )
    assert resp.status_code == 413


def test_upload_session_scoped_to_owner(client: TestClient) -> None:
    alice = register_and_login(client, "alice", "alice@example.com")
    pkg_id = _create_package(client, alice)
    session = _open_session(client, pkg_id, alice, filename="x.txt", size=10)
    upload_id = session["upload_id"]

    bob = register_and_login(client, "bob", "bob@example.com")
    # Bob doesn't own the package, so even the session URL is a 404 for him.
    assert (
        client.get(
            f"/api/packages/{pkg_id}/uploads/{upload_id}", headers=bob
        ).status_code
        == 404
    )


def test_abort_upload_discards_session(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    session = _open_session(client, pkg_id, headers, filename="x.txt", size=100)
    upload_id = session["upload_id"]
    _send_chunk(client, pkg_id, upload_id, headers, offset=0, data=b"a" * 40)

    resp = client.delete(
        f"/api/packages/{pkg_id}/uploads/{upload_id}", headers=headers
    )
    assert resp.status_code == 204
    with db_sessionmaker() as db:
        assert db.scalar(
            select(UploadSession).where(UploadSession.token == upload_id)
        ) is None


def test_prune_removes_stale_sessions_and_scratch(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    session = _open_session(client, pkg_id, headers, filename="x.txt", size=100)
    upload_id = session["upload_id"]
    _send_chunk(client, pkg_id, upload_id, headers, offset=0, data=b"a" * 40)

    # Backdate the session so the sweep considers it abandoned.
    with db_sessionmaker() as db:
        row = db.scalar(
            select(UploadSession).where(UploadSession.token == upload_id)
        )
        assert row is not None
        scratch_key = row.scratch_key
        row.updated_at = datetime(2000, 1, 1)
        db.commit()

    assert chunked.scratch_size(scratch_key) == 40
    removed = chunked.prune_upload_sessions(ttl_hours=1)
    assert removed == 1
    assert chunked.scratch_size(scratch_key) == 0
    with db_sessionmaker() as db:
        assert db.scalar(
            select(UploadSession).where(UploadSession.token == upload_id)
        ) is None
