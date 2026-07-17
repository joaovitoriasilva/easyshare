"""Tests for settings validation, including the production security guard."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_production_rejects_default_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            secret_key="change-me-in-production-this-is-not-secure",
        )


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="a" * 20)


def test_production_allows_strong_config() -> None:
    settings = Settings(environment="production", secret_key="s" * 40)
    assert settings.is_production


def test_development_allows_insecure_defaults() -> None:
    settings = Settings(
        environment="development",
        secret_key="change-me-in-production-this-is-not-secure",
    )
    assert not settings.is_production
