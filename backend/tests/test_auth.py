"""Tests for authentication endpoints."""

from __future__ import annotations

import io

import pytest
from app.core.rate_limit import limiter
from fastapi.testclient import TestClient

from tests.conftest import register_and_login


def test_auth_config_exposes_limits(client: TestClient) -> None:
    resp = client.get("/api/auth/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["allow_registration"] is True
    assert body["max_file_size"] > 0


def test_me_usage_reports_quota_and_usage(client: TestClient) -> None:
    headers = register_and_login(client)
    # Fresh account: nothing stored yet, but the default quota is exposed.
    resp = client.get("/api/auth/me/usage", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["storage_used"] == 0
    assert body["storage_quota"] > 0

    # Uploading a file is reflected in the reported usage.
    pkg_id = client.post(
        "/api/packages", json={"name": "P"}, headers=headers
    ).json()["id"]
    client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")},
        headers=headers,
    )
    body = client.get("/api/auth/me/usage", headers=headers).json()
    assert body["storage_used"] == 5


def test_me_usage_requires_auth(client: TestClient) -> None:
    assert client.get("/api/auth/me/usage").status_code == 401


def test_change_password_succeeds_with_correct_current(client: TestClient) -> None:
    headers = register_and_login(client, "dave", "dave@example.com", "originalpass1")

    resp = client.post(
        "/api/auth/me/password",
        json={"current_password": "originalpass1", "new_password": "brandnewpass2"},
        headers=headers,
    )
    assert resp.status_code == 200

    # The old password stops working; the new one is accepted.
    assert (
        client.post(
            "/api/auth/login",
            data={"username": "dave", "password": "originalpass1"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            data={"username": "dave", "password": "brandnewpass2"},
        ).status_code
        == 200
    )


def test_change_password_rejects_wrong_current(client: TestClient) -> None:
    headers = register_and_login(client, "erin", "erin@example.com", "erinpass123")
    resp = client.post(
        "/api/auth/me/password",
        json={"current_password": "wrongpass", "new_password": "newpass12345"},
        headers=headers,
    )
    assert resp.status_code == 400
    # The password is unchanged: the original still logs in.
    assert (
        client.post(
            "/api/auth/login",
            data={"username": "erin", "password": "erinpass123"},
        ).status_code
        == 200
    )


def test_change_password_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/me/password",
        json={"current_password": "x", "new_password": "newpass12345"},
    )
    assert resp.status_code == 401


def test_change_password_validates_new_length(client: TestClient) -> None:
    headers = register_and_login(client, "fred", "fred@example.com", "fredpass123")
    resp = client.post(
        "/api/auth/me/password",
        json={"current_password": "fredpass123", "new_password": "short"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_register_and_login(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "bob@example.com",
            "username": "bob",
            "password": "password123",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "bob@example.com"
    assert "hashed_password" not in body

    login = client.post(
        "/api/auth/login",
        data={"username": "bob", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"


def test_login_with_email(client: TestClient) -> None:
    client.post(
        "/api/auth/register",
        json={
            "email": "carol@example.com",
            "username": "carol",
            "password": "password123",
        },
    )
    login = client.post(
        "/api/auth/login",
        data={"username": "carol@example.com", "password": "password123"},
    )
    assert login.status_code == 200


def test_duplicate_registration_rejected(client: TestClient) -> None:
    payload = {
        "email": "dup@example.com",
        "username": "dup",
        "password": "password123",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_login_wrong_password(client: TestClient) -> None:
    client.post(
        "/api/auth/register",
        json={"email": "e@example.com", "username": "eve", "password": "password123"},
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": "eve", "password": "wrongpass"},
    )
    assert resp.status_code == 401


def test_weak_password_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"email": "w@example.com", "username": "weak", "password": "short"},
    )
    assert resp.status_code == 422


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_share_access_token_cannot_be_used_as_user_token(client: TestClient) -> None:
    """A restricted-share download token must not authenticate a user session."""
    from app.core.security import create_share_access_token

    scoped = create_share_access_token("share-token", "user@example.com")
    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {scoped}"}
    )
    assert resp.status_code == 401
    headers = register_and_login(client)
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


def test_invalid_token_rejected(client: TestClient) -> None:
    resp = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer " + "not-a-valid-token"}
    )
    assert resp.status_code == 401


def test_login_rate_limited(client: TestClient) -> None:
    """The SENSITIVE limit returns 429 once the per-minute cap is exceeded."""
    limiter.enabled = True
    try:
        statuses = [
            client.post(
                "/api/auth/login",
                data={"username": "ghost", "password": "nope"},
            ).status_code
            for _ in range(11)
        ]
    finally:
        limiter.enabled = False
    assert statuses[-1] == 429
    assert 429 not in statuses[:10]


def test_login_locks_account_after_repeated_failures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An account locks (429) after exhausting its failed-attempt budget."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "login_max_failed_attempts", 3)
    monkeypatch.setattr(settings, "login_lockout_minutes", 15)
    register_and_login(client, "lockme", "lockme@example.com", "correctpass1")

    for _ in range(3):
        resp = client.post(
            "/api/auth/login",
            data={"username": "lockme", "password": "wrongpass"},
        )
        assert resp.status_code == 401

    # Now locked: even the correct password is refused, with a Retry-After hint.
    locked = client.post(
        "/api/auth/login",
        data={"username": "lockme", "password": "correctpass1"},
    )
    assert locked.status_code == 429
    assert locked.headers.get("Retry-After") is not None


def test_successful_login_resets_failed_attempts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A correct login clears the counter so earlier failures don't accumulate."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "login_max_failed_attempts", 3)
    register_and_login(client, "resetme", "resetme@example.com", "correctpass1")

    for _ in range(2):
        client.post(
            "/api/auth/login", data={"username": "resetme", "password": "nope"}
        )
    # A correct login resets the counter...
    assert (
        client.post(
            "/api/auth/login",
            data={"username": "resetme", "password": "correctpass1"},
        ).status_code
        == 200
    )
    # ...so two further failures do not reach the lock threshold.
    for _ in range(2):
        assert (
            client.post(
                "/api/auth/login", data={"username": "resetme", "password": "nope"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login",
            data={"username": "resetme", "password": "correctpass1"},
        ).status_code
        == 200
    )


def test_login_lockout_disabled_when_zero(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting the attempt budget to 0 disables lockout entirely."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "login_max_failed_attempts", 0)
    register_and_login(client, "nolock", "nolock@example.com", "correctpass1")

    for _ in range(5):
        assert (
            client.post(
                "/api/auth/login", data={"username": "nolock", "password": "nope"}
            ).status_code
            == 401
        )
    # Never locks; the correct password still works.
    assert (
        client.post(
            "/api/auth/login",
            data={"username": "nolock", "password": "correctpass1"},
        ).status_code
        == 200
    )
