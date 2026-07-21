"""Tests for the pluggable storage backends and the selection factory."""

from __future__ import annotations

import io
import os
import time
from unittest.mock import MagicMock

import pytest
from app.core.config import settings
from app.models.models import PackageFile
from app.services import storage as storage_module
from app.services.files import prune_orphaned_blobs
from app.services.storage import (
    FileTooLargeError,
    LocalStorageBackend,
    build_storage,
    content_disposition_attachment,
)
from app.services.storage_s3 import (
    S3StorageBackend,
    _measure,
)
from botocore.exceptions import ClientError
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from tests.conftest import register_and_login

# --- Factory selection -----------------------------------------------------


def test_build_storage_defaults_to_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setattr(settings, "storage_uri", "")
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    assert isinstance(build_storage(), LocalStorageBackend)


def test_build_storage_local_scheme(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setattr(settings, "storage_uri", f"local://{tmp_path}")
    backend = build_storage()
    assert isinstance(backend, LocalStorageBackend)
    assert str(backend.base_dir) == str(tmp_path)


def test_build_storage_s3_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "storage_uri", "s3://my-bucket/prefix?region=us-east-1"
    )
    assert isinstance(build_storage(), S3StorageBackend)


def test_build_storage_rejects_unknown_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "storage_uri", "ftp://nope")
    with pytest.raises(ValueError, match="Unsupported"):
        build_storage()


# --- Local backend download response ---------------------------------------


def test_local_download_response_is_file_response(tmp_path: object) -> None:
    backend = LocalStorageBackend(tmp_path)  # type: ignore[arg-type]
    key = backend.generate_key()
    backend.save(key, io.BytesIO(b"data"))
    response = backend.download_response(
        key, filename="report.txt", content_type="text/plain"
    )
    assert isinstance(response, FileResponse)
    assert response.media_type == "text/plain"


# --- S3 backend (mocked client) --------------------------------------------


def _s3() -> tuple[S3StorageBackend, MagicMock]:
    client = MagicMock()
    return S3StorageBackend(client, "bucket", "prefix"), client


def test_measure_returns_size_and_rewinds() -> None:
    source = io.BytesIO(b"hello world")
    source.read(4)  # advance the cursor first
    assert _measure(source) == 11
    assert source.tell() == 0


def test_s3_save_uploads_and_returns_size() -> None:
    backend, client = _s3()
    size = backend.save("key123", io.BytesIO(b"payload-bytes"), max_bytes=100)
    assert size == len(b"payload-bytes")
    args, _ = client.upload_fileobj.call_args
    assert args[1] == "bucket"
    assert args[2] == "prefix/key123"


def test_s3_save_rejects_oversized_before_upload() -> None:
    backend, client = _s3()
    with pytest.raises(FileTooLargeError):
        backend.save("k", io.BytesIO(b"x" * 50), max_bytes=10)
    client.upload_fileobj.assert_not_called()


def test_s3_open_stream_returns_body() -> None:
    backend, client = _s3()
    client.get_object.return_value = {"Body": io.BytesIO(b"abc")}
    with backend.open_stream("k") as stream:
        assert stream.read() == b"abc"
    client.get_object.assert_called_once_with(Bucket="bucket", Key="prefix/k")


def test_s3_delete_calls_delete_object() -> None:
    backend, client = _s3()
    backend.delete("k")
    client.delete_object.assert_called_once_with(Bucket="bucket", Key="prefix/k")


def test_s3_exists_true() -> None:
    backend, client = _s3()
    assert backend.exists("k") is True
    client.head_object.assert_called_once_with(Bucket="bucket", Key="prefix/k")


def test_s3_exists_false_on_missing() -> None:
    backend, client = _s3()
    client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404"}}, "HeadObject"
    )
    assert backend.exists("k") is False


def test_s3_exists_reraises_other_errors() -> None:
    backend, client = _s3()
    client.head_object.side_effect = ClientError(
        {"Error": {"Code": "403"}}, "HeadObject"
    )
    with pytest.raises(ClientError):
        backend.exists("k")


def test_s3_check_writable_translates_errors_to_oserror() -> None:
    backend, client = _s3()
    client.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "500"}}, "HeadBucket"
    )
    with pytest.raises(OSError, match="not reachable"):
        backend.check_writable()


def test_s3_download_response_redirects_to_presigned_url() -> None:
    backend, client = _s3()
    client.generate_presigned_url.return_value = "https://s3.example/signed"
    response = backend.download_response(
        "k", filename="report.pdf", content_type="application/pdf"
    )
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 307
    assert response.headers["location"] == "https://s3.example/signed"
    _, kwargs = client.generate_presigned_url.call_args
    params = kwargs["Params"]
    assert params["Key"] == "prefix/k"
    assert params["ResponseContentType"] == "application/pdf"
    assert params["ResponseContentDisposition"] == 'attachment; filename="report.pdf"'


def test_content_disposition_encodes_unicode() -> None:
    assert content_disposition_attachment("a.txt") == 'attachment; filename="a.txt"'
    assert content_disposition_attachment("résumé.txt").startswith(
        "attachment; filename*=utf-8''"
    )


# --- Object enumeration + orphaned-blob sweep ------------------------------


def test_local_iter_objects_skips_scratch_and_hidden(tmp_path: object) -> None:
    """``iter_objects`` reports real blobs but not scratch or bookkeeping files."""
    backend = LocalStorageBackend(tmp_path / "store")  # type: ignore[operator]
    backend.save("flatkey", io.BytesIO(b"a"))
    backend.save("12/34_readable.txt", io.BytesIO(b"bb"))
    # Scratch area and a readiness-probe leftover must be ignored.
    (backend.base_dir / "_incoming").mkdir()
    (backend.base_dir / "_incoming" / "scratch1").write_bytes(b"x")
    (backend.base_dir / ".healthcheck-abc").write_bytes(b"")

    found = dict(backend.iter_objects())
    assert set(found) == {"flatkey", "12/34_readable.txt"}
    assert all(isinstance(mtime, float) for mtime in found.values())


def test_prune_orphaned_blobs_removes_only_old_unreferenced(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    """The sweep deletes old unreferenced blobs, keeping referenced/recent ones."""
    headers = register_and_login(client)
    pkg_id = client.post(
        "/api/packages", json={"name": "P"}, headers=headers
    ).json()["id"]
    client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=headers,
    )
    with db_sessionmaker() as session:
        referenced_key = session.scalar(select(PackageFile.storage_key))
    assert referenced_key is not None

    base = storage_module.storage.base_dir
    old_time = time.time() - 3 * 3600
    # A referenced blob is kept even when old (proves the reference guard).
    referenced_path = base / referenced_key
    os.utime(referenced_path, (old_time, old_time))
    # An old, unreferenced blob is an orphan and must be removed.
    old_orphan = base / "old_orphan_key"
    old_orphan.write_bytes(b"orphan")
    os.utime(old_orphan, (old_time, old_time))
    # A recent, unreferenced blob is protected by the age guard (it could be an
    # upload whose row is about to commit).
    recent_orphan = base / "recent_orphan_key"
    recent_orphan.write_bytes(b"new orphan")

    removed = prune_orphaned_blobs(retention_hours=1)

    assert removed == 1
    assert not old_orphan.exists()
    assert recent_orphan.exists()
    assert storage_module.storage.exists(referenced_key)


def test_prune_orphaned_blobs_disabled_is_noop(
    client: TestClient,
) -> None:
    """A non-positive retention disables the sweep entirely."""
    base = storage_module.storage.base_dir
    base.mkdir(parents=True, exist_ok=True)
    orphan = base / "would_be_orphan"
    orphan.write_bytes(b"x")
    os.utime(orphan, (time.time() - 10 * 3600, time.time() - 10 * 3600))
    assert prune_orphaned_blobs(retention_hours=0) == 0
    assert orphan.exists()
