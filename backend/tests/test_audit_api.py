"""Tests for the audit read API (owner-scoped and admin-wide)."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.models import User
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


def test_admin_endpoint_requires_admin(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    alice = register_and_login(client, "alice", "alice@example.com")
    _share_with_download(client, alice)

    # A normal user cannot read the global log.
    assert client.get("/api/audit", headers=alice).status_code == 403

    # Promote alice in the database.
    with db_sessionmaker() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        assert user is not None
        user.is_admin = True
        db.commit()

    resp = client.get("/api/audit", headers=alice)
    assert resp.status_code == 200
    actions = {e["action"] for e in resp.json()["items"]}
    # The global log includes account-level events that /mine excludes.
    assert "user.register" in actions
    assert "login.success" in actions


def test_me_reports_admin_flag(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    headers = register_and_login(client, "alice", "alice@example.com")
    assert client.get("/api/auth/me", headers=headers).json()["is_admin"] is False

    with db_sessionmaker() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        assert user is not None
        user.is_admin = True
        db.commit()

    assert client.get("/api/auth/me", headers=headers).json()["is_admin"] is True


def test_admin_email_promotes_on_register(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "admin_emails", ["boss@example.com"])
    client.post(
        "/api/auth/register",
        json={
            "email": "boss@example.com",
            "username": "boss",
            "password": "supersecret1",
        },
    )
    login = client.post(
        "/api/auth/login", data={"username": "boss", "password": "supersecret1"}
    )
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get("/api/auth/me", headers=headers).json()["is_admin"] is True
