"""Tests for the security audit trail (audit_log table)."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta

from app.core.audit import prune_audit_events
from app.models.models import AuditEvent
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from tests.conftest import register_and_login


def _actions(db_sessionmaker: sessionmaker) -> list[str]:
    with db_sessionmaker() as db:
        return [
            e.action
            for e in db.scalars(select(AuditEvent).order_by(AuditEvent.id))
        ]


def _events(db_sessionmaker: sessionmaker, action: str) -> list[AuditEvent]:
    with db_sessionmaker() as db:
        return list(
            db.scalars(select(AuditEvent).where(AuditEvent.action == action))
        )


def _restricted_share(client: TestClient, headers: dict[str, str]) -> tuple[str, int]:
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
        json={"visibility": "restricted", "allowed_emails": ["ok@example.com"]},
        headers=headers,
    ).json()["token"]
    return token, file_id


def test_register_and_login_are_audited(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    register_and_login(client)
    actions = _actions(db_sessionmaker)
    assert "user.register" in actions
    assert "login.success" in actions


def test_register_event_records_admin_flag(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    register_and_login(client, "first", "first@example.com")
    register_and_login(client, "second", "second@example.com")
    with db_sessionmaker() as db:
        events = list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.action == "user.register")
                .order_by(AuditEvent.id)
            )
        )
    assert json.loads(events[0].detail) == {"is_admin": True}
    assert json.loads(events[1].detail) == {"is_admin": False}


def test_failed_login_is_audited(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    client.post(
        "/api/auth/register",
        json={
            "email": "alice@example.com",
            "username": "alice",
            "password": "supersecret1",
        },
    )
    resp = client.post(
        "/api/auth/login", data={"username": "alice", "password": "wrong"}
    )
    assert resp.status_code == 401

    events = _events(db_sessionmaker, "login.failure")
    assert len(events) == 1
    assert events[0].actor == "alice"
    # The request middleware stamps every audited event with a request id.
    assert events[0].request_id


def test_share_enable_access_and_download_are_audited(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    headers = register_and_login(client)
    token, file_id = _restricted_share(client, headers)

    unlocked = client.post(
        f"/api/s/{token}/access", json={"email": "ok@example.com"}
    ).json()
    access = unlocked["download_token"]
    assert (
        client.get(
            f"/api/s/{token}/files/{file_id}/download", params={"access": access}
        ).status_code
        == 200
    )

    actions = set(_actions(db_sessionmaker))
    assert {"share.enable", "share.access.granted", "share.download"} <= actions

    download = _events(db_sessionmaker, "share.download")[0]
    assert download.actor == "ok@example.com"
    assert download.target == f"share:{token[:8]}"


def test_prune_audit_events_removes_old_events(
    db_sessionmaker: sessionmaker,
) -> None:
    now = datetime.now(UTC)
    with db_sessionmaker() as db:
        db.add_all(
            [
                AuditEvent(action="old", created_at=now - timedelta(days=40)),
                AuditEvent(action="recent", created_at=now - timedelta(days=5)),
            ]
        )
        db.commit()

    removed = prune_audit_events(retention_days=30)

    assert removed == 1
    assert _actions(db_sessionmaker) == ["recent"]


def test_prune_audit_events_disabled_keeps_everything(
    db_sessionmaker: sessionmaker,
) -> None:
    with db_sessionmaker() as db:
        db.add(
            AuditEvent(
                action="ancient",
                created_at=datetime.now(UTC) - timedelta(days=999),
            )
        )
        db.commit()

    assert prune_audit_events(retention_days=0) == 0
    assert _actions(db_sessionmaker) == ["ancient"]


def test_denied_share_access_is_audited(
    client: TestClient, db_sessionmaker: sessionmaker
) -> None:
    headers = register_and_login(client)
    token, _ = _restricted_share(client, headers)

    denied = client.post(
        f"/api/s/{token}/access", json={"email": "intruder@example.com"}
    )
    assert denied.status_code == 403

    events = _events(db_sessionmaker, "share.access.denied")
    assert len(events) == 1
    assert events[0].actor == "intruder@example.com"
    assert events[0].target == f"share:{token[:8]}"


def test_response_carries_request_id_header(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.headers.get("x-request-id")
