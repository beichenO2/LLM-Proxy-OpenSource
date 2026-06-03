"""Pytest fixtures for backend tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.testclient import TestClient

from app.api.deps import get_db
from app.db.base import Base
import app.db.models  # noqa: F401 — register models on metadata
from app.db.models import DbMetadata
from app.main import create_app
from app.services.browser_session import create_session, COOKIE_NAME
from app.services.vault import VaultService


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Session, None, None]:
    """SQLite file DB in a temp dir; schema via create_all (fast) — not the Alembic production path."""
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("PRIVPORTAL_DATABASE_URL", url)
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def app() -> FastAPI:
    """FastAPI app factory instance for API tests."""
    return create_app()


@pytest.fixture
def client(app: FastAPI, db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with get_db overridden to the test session; vault unlocked + session cookie."""
    if db_session.scalar(select(DbMetadata).where(DbMetadata.id == 1)) is None:
        VaultService.create_new_database(db_session, "test-master-password")

    def override_get_db():
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    app.state.vault = VaultService()
    app.state.vault.unlock(db_session, "test-master-password")

    token = create_session(db_session, role="admin", username="admin")
    db_session.commit()

    with TestClient(app) as test_client:
        test_client.cookies.set(COOKIE_NAME, token)
        yield test_client

    app.dependency_overrides.clear()
