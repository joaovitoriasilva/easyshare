"""Liveness/readiness probe tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import NoReturn

from app.api.deps import get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_ok(client: TestClient) -> None:
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


class _BrokenSession:
    """A stand-in DB session whose execute() always fails, like a dead DB."""

    def execute(self, *args: object, **kwargs: object) -> NoReturn:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_ready_reports_503_when_db_unreachable(client: TestClient) -> None:
    """A broken DB connection surfaces as a 503, not a 500 or false positive."""

    def override_get_db() -> Generator[_BrokenSession]:
        yield _BrokenSession()

    app.dependency_overrides[get_db] = override_get_db
    try:
        resp = client.get("/api/ready")
        assert resp.status_code == 503
    finally:
        del app.dependency_overrides[get_db]

