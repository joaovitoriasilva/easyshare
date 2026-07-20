"""Tests for the buffered view/download counters (scale hotspot mitigation)."""

from __future__ import annotations

import io

from app.models.models import PackageFile, Share
from app.services.counters import counter_buffer
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from tests.conftest import register_and_login


def _setup_share(client: TestClient) -> tuple[int, int, str]:
    """Create a package with one file and an enabled share; return ids + token."""
    headers = register_and_login(client)
    pkg_id = client.post(
        "/api/packages",
        json={"name": "Pkg", "description": None},
        headers=headers,
    ).json()["id"]
    file_id = client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("a.txt", io.BytesIO(b"aaa"), "text/plain")},
        headers=headers,
    ).json()["id"]
    token = client.post(
        f"/api/packages/{pkg_id}/share", json={}, headers=headers
    ).json()["token"]
    return pkg_id, file_id, token


def test_counts_are_buffered_not_written_until_flush(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    _pkg_id, file_id, token = _setup_share(client)

    # Two views, one single-file download, one archive download.
    client.get(f"/api/s/{token}")
    client.get(f"/api/s/{token}")
    client.get(f"/api/s/{token}/files/{file_id}/download")
    client.get(f"/api/s/{token}/download")

    # Nothing is persisted yet: the increments live only in the buffer.
    with db_sessionmaker() as session:
        share = session.scalar(select(Share).where(Share.token == token))
        assert share is not None
        assert share.view_count == 0
        file = session.get(PackageFile, file_id)
        assert file is not None
        assert file.download_count == 0

    # Flush and confirm the buffered deltas land in the database exactly once.
    counter_buffer.flush()
    with db_sessionmaker() as session:
        share = session.scalar(select(Share).where(Share.token == token))
        assert share is not None
        assert share.view_count == 2
        file = session.get(PackageFile, file_id)
        assert file is not None
        assert file.download_count == 2

    # A second flush with an empty buffer is a no-op (counts don't double).
    counter_buffer.flush()
    with db_sessionmaker() as session:
        share = session.scalar(select(Share).where(Share.token == token))
        assert share is not None
        assert share.view_count == 2


def test_stats_include_buffered_and_flushed_counts(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    headers = register_and_login(client)
    pkg_id = client.post(
        "/api/packages", json={"name": "Pkg", "description": None}, headers=headers
    ).json()["id"]
    file_id = client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("a.txt", io.BytesIO(b"aaa"), "text/plain")},
        headers=headers,
    ).json()["id"]
    token = client.post(
        f"/api/packages/{pkg_id}/share", json={}, headers=headers
    ).json()["token"]

    client.get(f"/api/s/{token}")
    client.get(f"/api/s/{token}/files/{file_id}/download")

    # Buffered (not yet flushed): stats already reflect the pending delta.
    before = client.get(f"/api/packages/{pkg_id}/stats", headers=headers).json()
    assert before["views"] == 1
    assert before["file_downloads"] == {str(file_id): 1}

    # Flushing must not change what the owner sees (buffer moves into the DB).
    counter_buffer.flush()
    after = client.get(f"/api/packages/{pkg_id}/stats", headers=headers).json()
    assert after["views"] == 1
    assert after["file_downloads"] == {str(file_id): 1}
