"""Tests for vault extensions (status, session, lock/logout contract)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient

from app.api.deps import get_db
from app.db.models import BrowserSession, DbMetadata
from app.services.vault import VaultService


@pytest.fixture
def locked_client(app, db_session):
    """TestClient with DB initialized but vault locked."""
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

    with TestClient(app) as test_client:
        app.state.vault = VaultService()
        yield test_client

    app.dependency_overrides.clear()


def test_vault_status_locked_before_unlock(locked_client):
    r = locked_client.get("/api/vault/status")
    assert r.status_code == 200
    data = r.json()
    assert "locked" in data
    assert isinstance(data["locked"], bool)
    assert data["locked"] is True


def test_vault_status_unlocked_when_unlocked(client):
    r = client.get("/api/vault/status")
    assert r.status_code == 200
    assert r.json()["locked"] is False


def test_audit_log_records_vault_unlock(locked_client):
    r = locked_client.post(
        "/api/vault/unlock", json={"master_password": "test-master-password"}
    )
    assert r.status_code == 200
    r = locked_client.get("/api/audit-log")
    assert r.status_code == 200
    actions = [item["action"] for item in r.json()["items"]]
    assert "vault.unlock" in actions


def test_logout_revokes_only_this_session(locked_client, db_session):
    """POST /vault/logout revokes the calling browser's session without locking the vault."""
    r = locked_client.post(
        "/api/vault/unlock", json={"master_password": "test-master-password"}
    )
    assert r.status_code == 200

    sessions_before = db_session.scalars(select(BrowserSession)).all()
    assert len(sessions_before) >= 1

    r = locked_client.post("/api/vault/logout")
    assert r.status_code == 200
    assert r.json()["status"] == "logged_out"

    status = locked_client.get("/api/vault/status").json()
    assert status["locked"] is False, "vault stays unlocked after logout"
    assert status["has_session"] is False, "this browser has no session after logout"


def test_auto_session_when_unlocked(locked_client, db_session):
    """POST /vault/auto-session grants a readonly session without password when vault is unlocked."""
    r = locked_client.post(
        "/api/vault/unlock", json={"master_password": "test-master-password"}
    )
    assert r.status_code == 200

    locked_client.post("/api/vault/logout")

    status = locked_client.get("/api/vault/status").json()
    assert status["locked"] is False
    assert status["has_session"] is False

    r = locked_client.post(
        "/api/vault/auto-session",
        headers={
            "Origin": "http://127.0.0.1:5170",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "session_created"
    assert r.json()["role"] == "readonly"

    status = locked_client.get("/api/vault/status").json()
    assert status["has_session"] is True


def test_auto_session_when_locked(locked_client):
    """POST /vault/auto-session returns 423 when vault is locked."""
    r = locked_client.post(
        "/api/vault/auto-session",
        headers={
            "Origin": "http://127.0.0.1:5170",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert r.status_code == 423


def test_lock_requires_admin(locked_client, db_session):
    """POST /vault/lock is admin-only and globally locks the vault."""
    r = locked_client.post(
        "/api/vault/unlock", json={"master_password": "test-master-password"}
    )
    assert r.status_code == 200

    r = locked_client.post("/api/vault/lock")
    assert r.status_code == 200
    assert r.json()["status"] == "locked"

    status = locked_client.get("/api/vault/status").json()
    assert status["locked"] is True
