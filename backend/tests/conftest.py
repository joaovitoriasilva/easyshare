"""Shared pytest fixtures: isolated database, storage and API client."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.rate_limit import limiter
from app.db.session import Base
from app.main import app
from app.services import storage as storage_module

# Rate limiting is disabled by default in tests; the dedicated rate-limit test
# re-enables it explicitly.
limiter.enabled = False


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient]:
    """Yield a TestClient backed by an isolated in-memory DB and temp storage."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    # Redirect file storage to a temporary directory for isolation.
    storage_module.storage.base_dir = tmp_path / "storage"
    storage_module.storage.base_dir.mkdir(parents=True, exist_ok=True)

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


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
