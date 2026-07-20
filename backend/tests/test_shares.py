"""Tests for share management and public share access."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from app.api.routes import public as public_module
from app.core.config import settings
from app.models.models import ShareAccessCode
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

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


def test_restricted_download_requires_access_token(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    token = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "restricted", "allowed_emails": ["ok@example.com"]},
        headers=headers,
    ).json()["token"]

    unlocked = client.post(
        f"/api/s/{token}/access", json={"email": "ok@example.com"}
    ).json()
    file_id = unlocked["files"][0]["id"]
    access = unlocked["download_token"]
    assert access

    # No token -> unauthorized.
    assert (
        client.get(f"/api/s/{token}/files/{file_id}/download").status_code == 401
    )
    # Garbage token -> unauthorized.
    assert (
        client.get(
            f"/api/s/{token}/files/{file_id}/download",
            params={"access": "not-a-real-token"},
        ).status_code
        == 401
    )
    # Valid token -> ok, for both the single file and the archive.
    assert (
        client.get(
            f"/api/s/{token}/files/{file_id}/download",
            params={"access": access},
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/s/{token}/download", params={"access": access}
        ).status_code
        == 200
    )

    # The email is never exposed in the download URL; the raw email is rejected.
    assert (
        client.get(
            f"/api/s/{token}/files/{file_id}/download",
            params={"access": "ok@example.com"},
        ).status_code
        == 401
    )


def test_share_access_token_is_scoped_to_its_share(client: TestClient) -> None:
    """A token minted for one share must not unlock another."""
    headers = register_and_login(client)
    pkg_a = _package_with_files(client, headers)
    pkg_b = _package_with_files(client, headers)
    token_a = client.post(
        f"/api/packages/{pkg_a}/share",
        json={"visibility": "restricted", "allowed_emails": ["ok@example.com"]},
        headers=headers,
    ).json()["token"]
    token_b = client.post(
        f"/api/packages/{pkg_b}/share",
        json={"visibility": "restricted", "allowed_emails": ["ok@example.com"]},
        headers=headers,
    ).json()["token"]

    access_a = client.post(
        f"/api/s/{token_a}/access", json={"email": "ok@example.com"}
    ).json()["download_token"]
    file_b = client.post(
        f"/api/s/{token_b}/access", json={"email": "ok@example.com"}
    ).json()["files"][0]["id"]

    # Share A's token cannot download share B's file.
    assert (
        client.get(
            f"/api/s/{token_b}/files/{file_b}/download",
            params={"access": access_a},
        ).status_code
        == 401
    )


def test_removing_email_revokes_existing_access_token(client: TestClient) -> None:
    """Access is re-checked at download time, so removing an email revokes it."""
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    token = client.post(
        f"/api/packages/{pkg_id}/share",
        json={
            "visibility": "restricted",
            "allowed_emails": ["ok@example.com", "keep@example.com"],
        },
        headers=headers,
    ).json()["token"]

    unlocked = client.post(
        f"/api/s/{token}/access", json={"email": "ok@example.com"}
    ).json()
    file_id = unlocked["files"][0]["id"]
    access = unlocked["download_token"]

    # Owner removes the recipient's address from the allow-list.
    client.patch(
        f"/api/packages/{pkg_id}/share",
        json={"allowed_emails": ["keep@example.com"]},
        headers=headers,
    )

    # The previously issued token is now forbidden.
    assert (
        client.get(
            f"/api/s/{token}/files/{file_id}/download",
            params={"access": access},
        ).status_code
        == 403
    )


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


# --- Share expiry ----------------------------------------------------------


def test_share_with_future_expiry_is_accessible(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    resp = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "public", "expires_at": future},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["expires_at"] is not None
    token = resp.json()["token"]
    assert client.get(f"/api/s/{token}").status_code == 200


def test_expired_share_returns_404(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    token = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "public"},
        headers=headers,
    ).json()["token"]

    # Set the expiry into the past via the owner update endpoint.
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    updated = client.patch(
        f"/api/packages/{pkg_id}/share",
        json={"expires_at": past},
        headers=headers,
    )
    assert updated.status_code == 200
    assert client.get(f"/api/s/{token}").status_code == 404


def test_clearing_expiry_restores_access(client: TestClient) -> None:
    headers = register_and_login(client)
    pkg_id = _package_with_files(client, headers)
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    token = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "public", "expires_at": past},
        headers=headers,
    ).json()["token"]
    assert client.get(f"/api/s/{token}").status_code == 404

    # An explicit null clears the expiry and re-enables the share.
    client.patch(
        f"/api/packages/{pkg_id}/share",
        json={"expires_at": None},
        headers=headers,
    )
    assert client.get(f"/api/s/{token}").status_code == 200


# --- Restricted-share email verification -----------------------------------


def _enable_email(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Turn on email verification and capture the codes that would be sent."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    captured: dict[str, str] = {}

    def _capture(to: str, code: str, *, package_name: str) -> None:
        captured["to"] = to
        captured["code"] = code

    monkeypatch.setattr(public_module, "send_share_verification_code", _capture)
    return captured


def _restricted_share(client: TestClient, headers: dict[str, str]) -> str:
    pkg_id = _package_with_files(client, headers)
    return client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "restricted", "allowed_emails": ["guest@example.com"]},
        headers=headers,
    ).json()["token"]


def test_config_reports_email_verification_flag(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/api/auth/config").json()["email_verification_enabled"] is False
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    assert client.get("/api/auth/config").json()["email_verification_enabled"] is True


def test_access_sends_code_and_hides_files(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _enable_email(monkeypatch)
    headers = register_and_login(client)
    token = _restricted_share(client, headers)

    resp = client.post(
        f"/api/s/{token}/access", json={"email": "guest@example.com"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verification_required"] is True
    assert body["download_token"] is None
    assert body["files"] == []
    # A code was emailed to the allow-listed recipient.
    assert captured.get("to") == "guest@example.com"
    assert captured.get("code")


def test_verify_with_correct_code_unlocks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _enable_email(monkeypatch)
    headers = register_and_login(client)
    token = _restricted_share(client, headers)
    client.post(f"/api/s/{token}/access", json={"email": "guest@example.com"})

    resp = client.post(
        f"/api/s/{token}/verify",
        json={"email": "guest@example.com", "code": captured["code"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["download_token"]
    assert len(body["files"]) == 2


def test_verify_with_wrong_code_is_denied(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _enable_email(monkeypatch)
    headers = register_and_login(client)
    token = _restricted_share(client, headers)
    client.post(f"/api/s/{token}/access", json={"email": "guest@example.com"})

    wrong = "111111" if captured["code"] != "111111" else "222222"
    resp = client.post(
        f"/api/s/{token}/verify",
        json={"email": "guest@example.com", "code": wrong},
    )
    assert resp.status_code == 403


def test_verification_does_not_reveal_allow_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-allow-listed email gets the same response but no code is sent."""
    captured = _enable_email(monkeypatch)
    headers = register_and_login(client)
    token = _restricted_share(client, headers)

    resp = client.post(
        f"/api/s/{token}/access", json={"email": "intruder@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["verification_required"] is True
    # No code was sent to a non-allow-listed address.
    assert captured == {}


def test_verification_attempts_are_capped(
    client: TestClient,
    db_sessionmaker: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "share_verification_max_attempts", 1)
    captured = _enable_email(monkeypatch)
    headers = register_and_login(client)
    token = _restricted_share(client, headers)
    client.post(f"/api/s/{token}/access", json={"email": "guest@example.com"})

    wrong = "111111" if captured["code"] != "111111" else "222222"
    # First wrong guess exhausts the single-attempt budget.
    assert (
        client.post(
            f"/api/s/{token}/verify",
            json={"email": "guest@example.com", "code": wrong},
        ).status_code
        == 403
    )
    # Even the correct code is now rejected (the code was invalidated).
    assert (
        client.post(
            f"/api/s/{token}/verify",
            json={"email": "guest@example.com", "code": captured["code"]},
        ).status_code
        == 403
    )


def test_expired_verification_code_is_denied(
    client: TestClient,
    db_sessionmaker: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _enable_email(monkeypatch)
    headers = register_and_login(client)
    token = _restricted_share(client, headers)
    client.post(f"/api/s/{token}/access", json={"email": "guest@example.com"})

    # Backdate the stored code so it is already expired.
    with db_sessionmaker() as db:
        record = db.scalar(select(ShareAccessCode))
        assert record is not None
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

    resp = client.post(
        f"/api/s/{token}/verify",
        json={"email": "guest@example.com", "code": captured["code"]},
    )
    assert resp.status_code == 403


def test_verify_rejected_when_email_disabled(client: TestClient) -> None:
    """With no SMTP configured the verify endpoint has nothing to confirm."""
    headers = register_and_login(client)
    token = _restricted_share(client, headers)
    resp = client.post(
        f"/api/s/{token}/verify",
        json={"email": "guest@example.com", "code": "123456"},
    )
    assert resp.status_code == 400
