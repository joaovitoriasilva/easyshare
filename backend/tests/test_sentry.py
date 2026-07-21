"""Tests for optional server-side crash reporting (GlitchTip/Sentry)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.core.config import settings
from app.core.sentry import init_sentry


def test_crash_reporting_disabled_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no DSN configured the SDK is never initialised."""
    monkeypatch.setattr(settings, "glitchtip_dsn_backend", "")
    with patch("sentry_sdk.init") as mock_init:
        assert init_sentry() is False
        mock_init.assert_not_called()


def test_crash_reporting_initialised_with_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured DSN initialises Sentry with GlitchTip-compatible options."""
    monkeypatch.setattr(
        settings, "glitchtip_dsn_backend", "https://key@example.com/3"
    )
    monkeypatch.setattr(settings, "environment", "production")
    with patch("sentry_sdk.init") as mock_init:
        assert init_sentry() is True
        mock_init.assert_called_once()
        kwargs = mock_init.call_args.kwargs
        assert kwargs["dsn"] == "https://key@example.com/3"
        assert kwargs["environment"] == "production"
        # GlitchTip does not support release-health sessions.
        assert kwargs["auto_session_tracking"] is False
        # Performance sampling is kept low to bound data volume.
        assert kwargs["traces_sample_rate"] == 0.01
