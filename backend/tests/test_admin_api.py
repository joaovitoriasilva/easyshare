"""Tests for first-user-admin bootstrap and admin user management."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient


def _register(
    client: TestClient, username: str, email: str, password: str = "supersecret1"
) -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _login(
    client: TestClient, username: str, password: str = "supersecret1"
) -> dict[str, str]:
    resp = client.post(
        "/api/auth/login", data={"username": username, "password": password}
    )
    return {"Authorization": "Bearer " + resp.json()["access_token"]}


def test_first_user_is_admin_others_are_not(client: TestClient) -> None:
    first = _register(client, "first", "first@example.com")
    assert first["is_admin"] is True

    second = _register(client, "second", "second@example.com")
    assert second["is_admin"] is False


def test_admin_lists_users(client: TestClient) -> None:
    admin_headers = _login_after_register(client, "admin", "admin@example.com")
    _register(client, "bob", "bob@example.com")
    _register(client, "carol", "carol@example.com")

    resp = client.get("/api/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert {u["username"] for u in body["items"]} == {"admin", "bob", "carol"}


def test_admin_can_promote_and_deactivate(client: TestClient) -> None:
    admin_headers = _login_after_register(client, "admin", "admin@example.com")
    bob = _register(client, "bob", "bob@example.com")
    bob_headers = _login(client, "bob")

    promoted = client.patch(
        f"/api/admin/users/{bob['id']}",
        json={"is_admin": True},
        headers=admin_headers,
    )
    assert promoted.status_code == 200
    assert promoted.json()["is_admin"] is True

    deactivated = client.patch(
        f"/api/admin/users/{bob['id']}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    # A deactivated user can no longer authenticate.
    assert client.get("/api/auth/me", headers=bob_headers).status_code == 401


def test_admin_cannot_lock_themselves_out(client: TestClient) -> None:
    admin = _register(client, "admin", "admin@example.com")
    admin_headers = _login(client, "admin")

    demote = client.patch(
        f"/api/admin/users/{admin['id']}",
        json={"is_admin": False},
        headers=admin_headers,
    )
    assert demote.status_code == 400

    deactivate = client.patch(
        f"/api/admin/users/{admin['id']}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate.status_code == 400


def test_admin_update_rejects_duplicate_identity(client: TestClient) -> None:
    admin_headers = _login_after_register(client, "admin", "admin@example.com")
    bob = _register(client, "bob", "bob@example.com")
    _register(client, "carol", "carol@example.com")

    resp = client.patch(
        f"/api/admin/users/{bob['id']}",
        json={"email": "carol@example.com"},
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_non_admin_cannot_manage_users(client: TestClient) -> None:
    admin = _register(client, "admin", "admin@example.com")
    _register(client, "bob", "bob@example.com")
    bob_headers = _login(client, "bob")

    assert client.get("/api/admin/users", headers=bob_headers).status_code == 403
    assert (
        client.patch(
            f"/api/admin/users/{admin['id']}",
            json={"is_admin": True},
            headers=bob_headers,
        ).status_code
        == 403
    )


def _login_after_register(
    client: TestClient, username: str, email: str
) -> dict[str, str]:
    _register(client, username, email)
    return _login(client, username)


def test_admin_can_delete_user(client: TestClient) -> None:
    admin_headers = _login_after_register(client, "admin", "admin@example.com")
    bob = _register(client, "bob", "bob@example.com")

    resp = client.delete(f"/api/admin/users/{bob['id']}", headers=admin_headers)
    assert resp.status_code == 200

    listed = client.get("/api/admin/users", headers=admin_headers)
    assert {u["username"] for u in listed.json()["items"]} == {"admin"}


def test_admin_cannot_delete_self(client: TestClient) -> None:
    admin = _register(client, "admin", "admin@example.com")
    admin_headers = _login(client, "admin")

    resp = client.delete(f"/api/admin/users/{admin['id']}", headers=admin_headers)
    assert resp.status_code == 400


def test_non_admin_cannot_delete_user(client: TestClient) -> None:
    admin = _register(client, "admin", "admin@example.com")
    _register(client, "bob", "bob@example.com")
    bob_headers = _login(client, "bob")

    resp = client.delete(f"/api/admin/users/{admin['id']}", headers=bob_headers)
    assert resp.status_code == 403


def test_admin_can_set_quota_and_see_usage(client: TestClient) -> None:
    admin_headers = _login_after_register(client, "admin", "admin@example.com")
    bob = _register(client, "bob", "bob@example.com")

    updated = client.patch(
        f"/api/admin/users/{bob['id']}",
        json={"storage_quota": 12345},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["storage_quota"] == 12345
    assert body["storage_used"] == 0

    listing = client.get("/api/admin/users", headers=admin_headers).json()
    bob_row = next(u for u in listing["items"] if u["username"] == "bob")
    assert bob_row["storage_quota"] == 12345
    assert bob_row["storage_used"] == 0


def test_admin_quota_override_is_enforced(client: TestClient) -> None:
    admin_headers = _login_after_register(client, "admin", "admin@example.com")
    bob = _register(client, "bob", "bob@example.com")
    bob_headers = _login(client, "bob")

    client.patch(
        f"/api/admin/users/{bob['id']}",
        json={"storage_quota": 4},
        headers=admin_headers,
    )
    pkg_id = client.post(
        "/api/packages",
        json={"name": "p", "description": None},
        headers=bob_headers,
    ).json()["id"]
    resp = client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("a.txt", io.BytesIO(b"toolarge"), "text/plain")},
        headers=bob_headers,
    )
    assert resp.status_code == 413


def test_admin_can_set_all_quotas(client: TestClient) -> None:
    admin_headers = _login_after_register(client, "admin", "admin@example.com")
    _register(client, "bob", "bob@example.com")
    _register(client, "carol", "carol@example.com")

    resp = client.patch(
        "/api/admin/users/quota",
        json={"storage_quota": 5000},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 3

    listing = client.get("/api/admin/users", headers=admin_headers).json()
    assert all(u["storage_quota"] == 5000 for u in listing["items"])


def test_non_admin_cannot_set_all_quotas(client: TestClient) -> None:
    _register(client, "admin", "admin@example.com")
    _register(client, "bob", "bob@example.com")
    bob_headers = _login(client, "bob")

    resp = client.patch(
        "/api/admin/users/quota",
        json={"storage_quota": 5000},
        headers=bob_headers,
    )
    assert resp.status_code == 403


def test_admin_can_reset_user_password(client: TestClient) -> None:
    admin_headers = _login_after_register(client, "admin", "admin@example.com")
    bob = _register(client, "bob", "bob@example.com", "bobpass1234")

    resp = client.post(
        f"/api/admin/users/{bob['id']}/password",
        json={"new_password": "resetpass5678"},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    # Bob's original password no longer works; the reset one does.
    assert (
        client.post(
            "/api/auth/login",
            data={"username": "bob", "password": "bobpass1234"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login",
            data={"username": "bob", "password": "resetpass5678"},
        ).status_code
        == 200
    )


def test_non_admin_cannot_reset_password(client: TestClient) -> None:
    admin = _register(client, "admin", "admin@example.com")
    _register(client, "bob", "bob@example.com")
    bob_headers = _login(client, "bob")

    resp = client.post(
        f"/api/admin/users/{admin['id']}/password",
        json={"new_password": "hijackpass99"},
        headers=bob_headers,
    )
    assert resp.status_code == 403


def test_reset_password_unknown_user_returns_404(client: TestClient) -> None:
    admin_headers = _login_after_register(client, "admin", "admin@example.com")
    resp = client.post(
        "/api/admin/users/9999/password",
        json={"new_password": "whatever12345"},
        headers=admin_headers,
    )
    assert resp.status_code == 404
