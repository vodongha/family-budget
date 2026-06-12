"""Test fixtures. Pure logic runs against SQLite in-memory (fast, no Oracle needed).

The app's get_session dependency is overridden to use the in-memory engine.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_session
from app.main import app


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    """Register a family + user and return Authorization headers for it."""
    client.post(
        "/auth/register",
        json={
            "email": "dad@example.com",
            "password": "s3cret-pass",
            "display_name": "Dad",
            "family_name": "Vo Family",
        },
    )
    login = client.post(
        "/auth/login",
        data={"username": "dad@example.com", "password": "s3cret-pass"},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
