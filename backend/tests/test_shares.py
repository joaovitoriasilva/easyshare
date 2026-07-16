"""Tests for share management and public share access."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from tests.conftest import register_and_login


def _package_with_files(client: TestClient, headers: dict[str, str]) -> int:
    pkg_id = client.post(
        "/api/packages",
        json={"name": "Docs", "description": None},
        headers=headers,
    ).json()["id"]
    for name, data in [("a.txt", b"aaa"), ("b.txt", b"bbbb")]:
        client.post(
            f"/api/packages/{pkg_id}/files",
            files={"file": (name, io.BytesIO(data), "text/plain")},
            headers=headers,
        )
    return pkg_id


def test_enable_public_share_and_view(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)

    resp = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "public", "allowed_emails": []},
        headers=headers,
    )
    assert resp.status_code == 201
    token = resp.json()["token"]
    assert token

    view = client.get(f"/api/s/{token}")
    assert view.status_code == 200
    body = view.json()
    assert body["requires_email"] is False
    assert len(body["files"]) == 2


def test_view_requires_enabled_share(client: TestClient) -> None:
    assert client.get("/api/s/does-not-exist").status_code == 404


def test_disabled_share_not_accessible(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    token = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "public"},
        headers=headers,
    ).json()["token"]

    client.patch(
        f"/api/packages/{pkg_id}/share",
        json={"is_enabled": False},
        headers=headers,
    )
    assert client.get(f"/api/s/{token}").status_code == 404


def test_restricted_share_hides_files_until_email(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    token = client.post(
        f"/api/packages/{pkg_id}/share",
        json={
            "visibility": "restricted",
            "allowed_emails": ["guest@example.com"],
        },
        headers=headers,
    ).json()["token"]

    view = client.get(f"/api/s/{token}")
    assert view.status_code == 200
    assert view.json()["requires_email"] is True
    assert view.json()["files"] == []

    # Wrong email is forbidden.
    denied = client.post(
        f"/api/s/{token}/access", json={"email": "intruder@example.com"}
    )
    assert denied.status_code == 403

    # Allowed email unlocks the files (case-insensitive).
    allowed = client.post(
        f"/api/s/{token}/access", json={"email": "GUEST@example.com"}
    )
    assert allowed.status_code == 200
    assert len(allowed.json()["files"]) == 2


def test_restricted_requires_email_list(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    resp = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "restricted", "allowed_emails": []},
        headers=headers,
    )
    assert resp.status_code == 400


def test_update_share_resaving_existing_emails(client: TestClient) -> None:
    """Re-saving a restricted share with an unchanged email must not 500.

    Regression: clearing and re-adding the same address made the flush emit an
    INSERT before the DELETE, violating the (share_id, email) unique constraint.
    """
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "restricted", "allowed_emails": ["guest@example.com"]},
        headers=headers,
    )

    # Frontend "Save changes" resends the emails it loaded, unchanged.
    unchanged = client.patch(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "restricted", "allowed_emails": ["guest@example.com"]},
        headers=headers,
    )
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["allowed_emails"] == ["guest@example.com"]

    # Keeping one address while adding and removing others reconciles cleanly.
    changed = client.patch(
        f"/api/packages/{pkg_id}/share",
        json={
            "visibility": "restricted",
            "allowed_emails": ["GUEST@example.com", "second@example.com"],
        },
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert sorted(changed.json()["allowed_emails"]) == [
        "guest@example.com",
        "second@example.com",
    ]


def test_download_selected_files_as_zip(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    share = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "public"},
        headers=headers,
    ).json()
    token = share["token"]

    files = client.get(f"/api/s/{token}").json()["files"]
    first_id = files[0]["id"]

    # Selected subset.
    resp = client.get(f"/api/s/{token}/download", params={"file_ids": [first_id]})
    assert resp.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    assert len(archive.namelist()) == 1

    # All files.
    resp_all = client.get(f"/api/s/{token}/download")
    archive_all = zipfile.ZipFile(io.BytesIO(resp_all.content))
    assert len(archive_all.namelist()) == 2


def test_restricted_download_requires_valid_email(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    token = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "restricted", "allowed_emails": ["ok@example.com"]},
        headers=headers,
    ).json()["token"]

    files = client.post(
        f"/api/s/{token}/access", json={"email": "ok@example.com"}
    ).json()["files"]
    file_id = files[0]["id"]

    # No email -> unauthorized.
    assert (
        client.get(f"/api/s/{token}/files/{file_id}/download").status_code == 401
    )
    # Wrong email -> forbidden.
    assert (
        client.get(
            f"/api/s/{token}/files/{file_id}/download",
            params={"email": "no@example.com"},
        ).status_code
        == 403
    )
    # Valid email -> ok.
    ok = client.get(
        f"/api/s/{token}/files/{file_id}/download",
        params={"email": "ok@example.com"},
    )
    assert ok.status_code == 200


def test_cannot_share_others_package(client: TestClient) -> None:
    alice = register_and_login(client, "alice", "alice@example.com")
    pkg_id = _package_with_files(client, alice)
    bob = register_and_login(client, "bob", "bob@example.com")
    resp = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "public"},
        headers=bob,
    )
    assert resp.status_code == 404
