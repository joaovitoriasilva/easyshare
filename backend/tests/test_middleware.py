"""Tests for custom ASGI middleware."""

from __future__ import annotations

import io

from app.core.middleware import MaxBodySizeMiddleware, SecurityHeadersMiddleware
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient


def _echo_app(max_body_size: int, json_max_body_size: int | None = None) -> FastAPI:
    """A minimal app guarded by the body-size middleware, echoing its payload."""
    app = FastAPI()

    @app.post("/echo")
    def echo(payload: dict[str, str]) -> dict[str, str]:
        return payload

    @app.post("/upload")
    def upload(file: UploadFile = File(...)) -> dict[str, str]:
        return {"filename": file.filename or ""}

    app.add_middleware(
        MaxBodySizeMiddleware,
        max_body_size=max_body_size,
        json_max_body_size=json_max_body_size,
    )
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


def test_json_body_held_to_smaller_cap_than_multipart() -> None:
    """Non-multipart bodies use the (smaller) JSON cap, uploads the larger one."""
    # Large multipart cap, tiny JSON cap: a small JSON document is refused...
    client = TestClient(_echo_app(max_body_size=10_000_000, json_max_body_size=8))
    assert client.post("/echo", json={"hello": "world"}).status_code == 413

    # ...while a multipart upload comfortably under the multipart cap passes,
    # even though it is far larger than the JSON cap.
    resp = client.post(
        "/upload",
        files={"file": ("a.txt", io.BytesIO(b"0" * 1000), "text/plain")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"filename": "a.txt"}


def _secured_app() -> FastAPI:
    """A minimal app wrapped only by the security-headers middleware."""
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(SecurityHeadersMiddleware)
    return app


def test_static_security_headers_always_present() -> None:
    """The CSP/nosniff/frame headers are stamped on every response."""
    resp = TestClient(_secured_app()).get("/ping")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in resp.headers


def test_hsts_present_over_https() -> None:
    """HSTS is stamped when the (proxy-aware) request scheme is https."""
    client = TestClient(_secured_app(), base_url="https://testserver")
    resp = client.get("/ping")
    hsts = resp.headers.get("strict-transport-security")
    assert hsts is not None
    assert "max-age=" in hsts
    assert "includeSubDomains" in hsts


def test_hsts_absent_over_http() -> None:
    """HSTS is never sent over plain HTTP so local dev isn't pinned to TLS."""
    resp = TestClient(_secured_app()).get("/ping")
    assert "strict-transport-security" not in resp.headers

