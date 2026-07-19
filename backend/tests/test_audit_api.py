"""Tests for the audit read API (owner-scoped and admin-wide)."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from tests.conftest import register_and_login


def _share_with_download(
    client: TestClient, headers: dict[str, str], email: str = "ok@example.com"
) -> int:
    pkg_id = client.post(
        "/api/packages",
        json={"name": "Docs", "description": None},
        headers=headers,
    ).json()["id"]
    file_id = client.post(
        f"/api/packages/{pkg_id}/files",
        files={"file": ("a.txt", io.BytesIO(b"aaa"), "text/plain")},
        headers=headers,
    ).json()["id"]
    token = client.post(
        f"/api/packages/{pkg_id}/share",
        json={"visibility": "restricted", "allowed_emails": [email]},
        headers=headers,
    ).json()["token"]
    unlocked = client.post(f"/api/s/{token}/access", json={"email": email}).json()
    client.get(
        f"/api/s/{token}/files/{file_id}/download",
        params={"access": unlocked["download_token"]},
    )
    return pkg_id


def test_my_activity_is_scoped_to_owner(client: TestClient) -> None:
    alice = register_and_login(client, "alice", "alice@example.com")
    pkg_id = _share_with_download(client, alice)
    bob = register_and_login(client, "bob", "bob@example.com")

    mine = client.get("/api/audit/mine", headers=alice).json()
    actions = {e["action"] for e in mine["items"]}
    assert {"share.enable", "share.access.granted", "share.download"} <= actions
    assert all(e["package_id"] == pkg_id for e in mine["items"])
    assert mine["total"] >= 3

    # Bob owns nothing, so his activity feed is empty.
    bob_mine = client.get("/api/audit/mine", headers=bob).json()
    assert bob_mine["items"] == []
    assert bob_mine["total"] == 0


def test_my_activity_action_filter(client: TestClient) -> None:
    alice = register_and_login(client)
    _share_with_download(client, alice)

    resp = client.get(
        "/api/audit/mine", params={"action": "share.download"}, headers=alice
    ).json()
    assert resp["items"]
    assert all(e["action"] == "share.download" for e in resp["items"])
    # Parsed JSON detail is exposed as an object.
    assert resp["items"][0]["detail"]["filename"] == "a.txt"


def test_audit_page_reports_retention_days(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "audit_retention_days", 90)
    headers = register_and_login(client)

    # Both the owner activity feed and the admin-wide log expose the policy.
    mine = client.get("/api/audit/mine", headers=headers).json()
    assert mine["retention_days"] == 90
    all_log = client.get("/api/audit", headers=headers).json()
    assert all_log["retention_days"] == 90


def test_admin_endpoint_requires_admin(client: TestClient) -> None:
    # The first registered user is an admin; the second is not.
    admin = register_and_login(client, "admin", "admin@example.com")
    _share_with_download(client, admin)
    bob = register_and_login(client, "bob", "bob@example.com")

    # A normal user cannot read the global log.
    assert client.get("/api/audit", headers=bob).status_code == 403

    resp = client.get("/api/audit", headers=admin)
    assert resp.status_code == 200
    actions = {e["action"] for e in resp.json()["items"]}
    # The global log includes account-level events that /mine excludes.
    assert "user.register" in actions
    assert "login.success" in actions
