"""Tests for custom ASGI middleware."""

from __future__ import annotations

from app.core.middleware import MaxBodySizeMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _echo_app(max_body_size: int) -> FastAPI:
    """A minimal app guarded by the body-size middleware, echoing its payload."""
    app = FastAPI()

    @app.post("/echo")
    def echo(payload: dict[str, str]) -> dict[str, str]:
        return payload

    app.add_middleware(MaxBodySizeMiddleware, max_body_size=max_body_size)
    return app


def test_body_within_limit_passes_through() -> None:
    client = TestClient(_echo_app(max_body_size=1024))
    resp = client.post("/echo", json={"hello": "world"})
    assert resp.status_code == 200
    assert resp.json() == {"hello": "world"}


def test_oversized_body_rejected_with_413_before_routing() -> None:
    """A declared Content-Length over the cap is refused before the body is read."""
    client = TestClient(_echo_app(max_body_size=8))
    resp = client.post("/echo", json={"hello": "world"})
    assert resp.status_code == 413
    assert resp.json() == {"detail": "Request body too large"}
