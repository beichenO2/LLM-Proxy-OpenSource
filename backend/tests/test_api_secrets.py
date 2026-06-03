"""Tests for /api/secrets (SCRT-01, SCRT-04–07, D-22, D-36)."""

from __future__ import annotations

import httpx
from sqlalchemy import select
from starlette.testclient import TestClient

from app.api.deps import get_db, get_vault
from app.db.models import DbMetadata
from app.services.vault import VaultService


def test_create_secret_metadata_only_response(client):
    r = client.post(
        "/api/secrets",
        json={
            "key": "secret.openai.default.api_key",
            "value": "sk-secret",
            "project_id": None,
        },
    )
    assert r.status_code == 201
    assert "value" not in r.json()


def test_secret_list_excludes_value(client):
    client.post(
        "/api/secrets",
        json={
            "key": "secret.openai.other.key",
            "value": "v",
            "project_id": None,
        },
    )
    r = client.get("/api/secrets")
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert "value" not in item


def test_patch_enable_disable(client):
    create = client.post(
        "/api/secrets",
        json={
            "key": "secret.toggle.enabled",
            "value": "secret-val",
            "project_id": None,
        },
    )
    assert create.status_code == 201
    sid = create.json()["id"]

    r = client.patch(f"/api/secrets/{sid}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    r = client.patch(f"/api/secrets/{sid}", json={"enabled": True})
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_rotate_sets_rotated_at(client):
    create = client.post(
        "/api/secrets",
        json={
            "key": "secret.rotate.sample",
            "value": "old-plain",
            "project_id": None,
        },
    )
    assert create.status_code == 201
    sid = create.json()["id"]

    r = client.post(f"/api/secrets/{sid}/rotate", json={"value": "new-plain"})
    assert r.status_code == 200
    data = r.json()
    assert data["rotated_at"] is not None


def test_connectivity_requires_base_url(client):
    create = client.post(
        "/api/secrets",
        json={
            "key": "secret.no.baseurl",
            "value": "x",
            "project_id": None,
        },
    )
    assert create.status_code == 201
    sid = create.json()["id"]

    r = client.post(f"/api/secrets/{sid}/test-connectivity")
    assert r.status_code == 400
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_vault_locked_on_create(app, db_session):
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

    try:
        with TestClient(app) as c:
            app.state.vault = VaultService()
            r = c.post(
                "/api/secrets",
                json={
                    "key": "secret.test.locked",
                    "value": "x",
                    "project_id": None,
                },
            )
            assert r.status_code == 423
            assert r.json()["code"] == "VAULT_LOCKED"
    finally:
        app.dependency_overrides.clear()


def test_connectivity_probe_success(client, monkeypatch):
    create = client.post(
        "/api/secrets",
        json={
            "key": "secret.probe.ok",
            "value": "x",
            "project_id": None,
            "base_url": "https://example.com",
        },
    )
    assert create.status_code == 201
    sid = create.json()["id"]

    class _Resp:
        status_code = 200

    class _Client:
        async def head(self, _url, follow_redirects=True):
            return _Resp()

        async def get(self, _url, follow_redirects=True):
            return _Resp()

    class _CM:
        async def __aenter__(self):
            return _Client()

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", lambda *_a, **_k: _CM())

    r = client.post(f"/api/secrets/{sid}/test-connectivity")
    assert r.status_code == 200
    data = r.json()
    assert data["reachable"] is True
    assert data["status_code"] == 200
