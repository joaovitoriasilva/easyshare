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


def test_distributed_requires_shared_rate_limit_store() -> None:
    with pytest.raises(ValidationError):
        Settings(deployment_profile="distributed", rate_limit_storage_uri="memory://")


def test_distributed_allows_redis_rate_limit_store() -> None:
    settings = Settings(
        deployment_profile="distributed",
        rate_limit_storage_uri="redis://localhost:6379/0",
        database_url="postgresql+psycopg://user:pass@db/easyshare",
    )
    assert settings.deployment_profile == "distributed"


def test_distributed_rejects_sqlite_database() -> None:
    with pytest.raises(ValidationError):
        Settings(
            deployment_profile="distributed",
            rate_limit_storage_uri="redis://localhost:6379/0",
            database_url="sqlite:///./easyshare.db",
        )


def test_local_profile_allows_in_memory_store() -> None:
    settings = Settings(
        deployment_profile="local", rate_limit_storage_uri="memory://"
    )
    assert settings.deployment_profile == "local"


def test_invalid_deployment_profile_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(deployment_profile="cluster")
