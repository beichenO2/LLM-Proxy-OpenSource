"""Tests for GET/POST /api/onboarding/* (ONBD-02, ONBD-04, ONBD-05)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.api.deps import get_db
from app.main import create_app
from app.services.vault import VaultService


def test_onboarding_status_shape_and_complete_flow(client) -> None:
    r = client.get("/api/onboarding/status")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"completed", "has_db", "has_vault"}
    assert isinstance(data["completed"], bool)
    assert data["has_db"] is True
    assert data["has_vault"] is True

    assert client.post("/api/onboarding/complete").status_code == 200
    r2 = client.get("/api/onboarding/status")
    assert r2.json()["completed"] is True


def test_import_demo_vault_locked_returns_423(app, db_session) -> None:
    def override_get_db():
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as tc:
            app.state.vault = VaultService()
            r = tc.post("/api/onboarding/import-demo")
        assert r.status_code == 423
        body = r.json()
        assert body.get("code") == "VAULT_LOCKED"
    finally:
        app.dependency_overrides.clear()


def test_import_demo_unlocked_returns_summary(client) -> None:
    r = client.post("/api/onboarding/import-demo")
    assert r.status_code == 200
    data = r.json()
    assert "project_id" in data
    assert data["secrets"] >= 2
    assert data["bindings"] >= 2


def test_init_db_creates_schema_on_empty_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "onboard_empty.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("PRIVPORTAL_DATABASE_URL", url)

    import app.db.session as session_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker as sa_sessionmaker

    orig_engine = session_mod.engine
    orig_local = session_mod.SessionLocal

    test_engine = create_engine(url, connect_args={"check_same_thread": False})
    test_session_local = sa_sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session_mod.engine = test_engine
    session_mod.SessionLocal = test_session_local

    try:
        test_app = create_app()
        with TestClient(test_app) as tc:
            r = tc.post("/api/onboarding/init-db")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        conn = sqlite3.connect(str(db_path))
        try:
            names = [
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            ]
            assert "db_metadata" in names
        finally:
            conn.close()
    finally:
        session_mod.engine = orig_engine
        session_mod.SessionLocal = orig_local
        test_engine.dispose()


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/onboarding/status", "GET"),
        ("/api/onboarding/complete", "POST"),
    ],
)
def test_onboarding_routes_exist(path: str, method: str, client) -> None:
    r = client.request(method, path)
    assert r.status_code != 404
