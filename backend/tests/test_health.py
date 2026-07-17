"""Liveness/readiness probe tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import NoReturn

from app.api.deps import get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker


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


class _ExplodingSession:
    """A DB session whose execute() raises a non-``SQLAlchemyError``.

    The readiness probe only catches ``SQLAlchemyError``, so this propagates
    uncaught and exercises the generic 500 exception handler instead.
    """

    def execute(self, *args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError("unexpected failure")


def test_unhandled_error_returns_json_500_with_request_id(
    db_sessionmaker: sessionmaker,
) -> None:
    """An uncaught exception yields a JSON 500 carrying the request id."""

    def override_get_db() -> Generator[_ExplodingSession]:
        yield _ExplodingSession()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/ready")
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "Internal server error"
        assert body["request_id"]
        assert resp.headers["x-request-id"] == body["request_id"]
    finally:
        del app.dependency_overrides[get_db]


