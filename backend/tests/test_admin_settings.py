"""Tests for the admin service-settings endpoint (security by design)."""

from __future__ import annotations

import json

from app.core.config import settings
from fastapi.testclient import TestClient

from tests.conftest import register_and_login


def test_settings_requires_admin(client: TestClient) -> None:
    # The first registered user is an admin; the second is a normal user.
    register_and_login(client, "admin", "admin@example.com")
    bob = register_and_login(client, "bob", "bob@example.com")

    assert client.get("/api/admin/settings", headers=bob).status_code == 403
    assert client.get("/api/admin/settings").status_code == 401


def test_settings_expose_safe_config_without_secrets(client: TestClient) -> None:
    admin = register_and_login(client)

    resp = client.get("/api/admin/settings", headers=admin)
    assert resp.status_code == 200
    body = resp.json()

    # A representative non-sensitive field is present and correct.
    assert body["app_name"] == settings.app_name
    assert body["database_backend"] == "sqlite"

    # Connection strings are reduced to a bare scheme: no host or credentials.
    for key in ("database_backend", "storage_backend", "rate_limit_backend"):
        assert "@" not in body[key]
        assert "/" not in body[key]

    # The safe email/verification knobs are exposed for administrators.
    assert body["email_verification_enabled"] == settings.email_verification_enabled
    assert body["smtp_use_tls"] == settings.smtp_use_tls
    assert body["smtp_timeout"] == settings.smtp_timeout
    assert (
        body["share_verification_code_ttl_minutes"]
        == settings.share_verification_code_ttl_minutes
    )
    assert (
        body["share_verification_max_attempts"]
        == settings.share_verification_max_attempts
    )

    # The signing secret and raw connection strings must never be exposed,
    # neither as fields nor anywhere in the serialised payload. The SMTP host,
    # login and password are likewise omitted (only the enabled flag is shown).
    assert "secret_key" not in body
    assert "database_url" not in body
    assert "storage_uri" not in body
    assert "smtp_host" not in body
    assert "smtp_username" not in body
    assert "smtp_password" not in body
    assert "smtp_from" not in body
    assert settings.secret_key not in json.dumps(body)
