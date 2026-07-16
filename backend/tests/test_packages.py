"""Tests for package CRUD and file upload/download."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import register_and_login


def _create_package(client: TestClient, headers: dict[str, str]) -> int:
    resp = client.post(
        "/api/packages",
        json={"name": "My Package", "description": "demo"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_and_list_packages(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)

    listing = client.get("/api/packages", headers=headers)
    assert listing.status_code == 200
    assert [p["id"] for p in listing.json()] == [pkg_id]


def test_list_packages_pagination(client: TestClient) -> None:
    headers = register_and_login(client)
    ids = {_create_package(client, headers) for _ in range(3)}

    page1 = client.get(
        "/api/packages", params={"limit": 2, "offset": 0}, headers=headers
    )
    assert page1.status_code == 200
    assert len(page1.json()) == 2

    page2 = client.get(
        "/api/packages", params={"limit": 2, "offset": 2}, headers=headers
    )
    assert len(page2.json()) == 1

    seen = {p["id"] for p in page1.json()} | {p["id"] for p in page2.json()}
    assert seen == ids

    # Bounds are validated.
    assert (
        client.get("/api/packages", params={"limit": 0}, headers=headers).status_code
        == 422
    )
    assert (
        client.get(
            "/api/packages", params={"limit": 101}, headers=headers
        ).status_code
        == 422
    )


def test_list_packages_includes_files(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("a.txt", io.BytesIO(b"data"), "text/plain")},
        headers=headers,
    )
    listing = client.get("/api/packages", headers=headers).json()
    assert listing[0]["id"] == pkg_id
    assert [f["filename"] for f in listing[0]["files"]] == ["a.txt"]


def test_package_requires_auth(client: TestClient) -> None:
    assert client.get("/api/packages").status_code == 401


def test_upload_and_download_file(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)

    resp = client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("hello.txt", io.BytesIO(b"hello world"), "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 201
    file_id = resp.json()["id"]
    assert resp.json()["size"] == 11

    download = client.get(
        f"/api/packages/{pkg_id}/files/{file_id}/download", headers=headers
    )
    assert download.status_code == 200
    assert download.content == b"hello world"


def test_cannot_access_others_package(client: TestClient) -> None:
    alice = register_and_login(client, "alice", "alice@example.com")
    pkg_id = _create_package(client, alice)

    bob = register_and_login(client, "bob", "bob@example.com")
    resp = client.get(f"/api/packages/{pkg_id}", headers=bob)
    assert resp.status_code == 404


def test_delete_package_removes_files(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("a.txt", io.BytesIO(b"data"), "text/plain")},
        headers=headers,
    )
    resp = client.delete(f"/api/packages/{pkg_id}", headers=headers)
    assert resp.status_code == 200
    assert client.get(f"/api/packages/{pkg_id}", headers=headers).status_code == 404


def test_update_package(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    resp = client.patch(
        f"/api/packages/{pkg_id}",
        json={"name": "Renamed"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


def test_upload_rejects_dangerous_extension(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    resp = client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("evil.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
        headers=headers,
    )
    assert resp.status_code == 400


def test_upload_strips_path_from_filename(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    resp = client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("../../etc/passwd.txt", io.BytesIO(b"data"), "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["filename"] == "passwd.txt"


def test_upload_rejects_oversized_file(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_file_size", 8)
    headers = register_and_login(client)
    pkg_id = _create_package(client, headers)
    resp = client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("big.txt", io.BytesIO(b"0123456789abcdef"), "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 413
