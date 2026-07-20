"""Shared pytest fixtures: isolated database, storage and API client."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from app.api.deps import get_db
from app.core import audit as audit_module
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import Base
from app.main import app
from app.services import chunked as chunked_module
from app.services import counters as counters_module
from app.services import storage as storage_module
from app.services.quota import reset_total_usage_cache
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Rate limiting is disabled by default in tests; the dedicated rate-limit test
# re-enables it explicitly.
limiter.enabled = False

# Keep the audit-retention background loop out of tests: with a positive default
# it would start under the TestClient lifespan and prune the shared in-memory
# database concurrently with test requests. The pruning logic is covered
# directly in test_audit.py.
settings.audit_retention_days = 0

# Keep the counter-flush background loop out of tests too: with the loop
# disabled, buffered view/download increments stay in memory and are surfaced by
# the stats endpoint (which adds the pending delta), so counting is deterministic
# without a timing-dependent flush racing the assertions.
settings.counter_flush_interval_seconds = 0


@pytest.fixture
def db_sessionmaker(tmp_path: Path) -> Generator[sessionmaker]:
    """Set up an isolated in-memory DB + temp storage; yield its session maker.

    Exposing the session maker lets tests inspect persisted state (e.g. the
    ``audit_log`` table) on the same engine the app writes to.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    # The instance-total cache is process-global; clear it so a value scanned on
    # a previous test's engine can't leak into this one.
    reset_total_usage_cache()

    def override_get_db() -> Generator:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # Redirect file storage to a temporary directory for isolation.
    storage_module.storage.base_dir = tmp_path / "storage"
    storage_module.storage.base_dir.mkdir(parents=True, exist_ok=True)
    # Isolate the resumable-upload scratch area and point its prune sweep at the
    # test engine.
    chunked_module.scratch_dir = tmp_path / "incoming"
    original_prune_sessionmaker = chunked_module.prune_sessionmaker
    chunked_module.prune_sessionmaker = TestingSessionLocal

    original_audit_sessionmaker = audit_module.audit_sessionmaker
    audit_module.audit_sessionmaker = TestingSessionLocal
    # Point counter flushing at the isolated engine and start from a clean
    # buffer so a previous test's pending deltas can't leak into this one.
    original_counter_sessionmaker = counters_module.counter_sessionmaker
    counters_module.counter_sessionmaker = TestingSessionLocal
    counters_module.counter_buffer.reset()
    app.dependency_overrides[get_db] = override_get_db
    yield TestingSessionLocal
    app.dependency_overrides.clear()
    audit_module.audit_sessionmaker = original_audit_sessionmaker
    counters_module.counter_sessionmaker = original_counter_sessionmaker
    counters_module.counter_buffer.reset()
    chunked_module.prune_sessionmaker = original_prune_sessionmaker
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_sessionmaker: sessionmaker) -> Generator[TestClient]:
    """Yield a TestClient backed by the isolated DB and temp storage."""
    with TestClient(app) as test_client:
        yield test_client


def register_and_login(
    client: TestClient,
    username: str = "alice",
    email: str = "alice@example.com",
    password: str = "supersecret1",
) -> dict[str, str]:
    """Register a user and return an Authorization header."""
    client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    token = resp.json()["access_token"]
    return {"Authorization": "Bearer " + token}
