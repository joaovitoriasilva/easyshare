"""Tests for the pluggable storage backends and the selection factory."""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from app.core.config import settings
from app.services.storage import (
    FileTooLargeError,
    LocalStorageBackend,
    build_storage,
)
from app.services.storage_s3 import (
    S3StorageBackend,
    _content_disposition,
    _measure,
)
from botocore.exceptions import ClientError
from fastapi.responses import FileResponse, RedirectResponse

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
    assert _content_disposition("a.txt") == 'attachment; filename="a.txt"'
    assert _content_disposition("résumé.txt").startswith(
        "attachment; filename*=utf-8''"
    )
