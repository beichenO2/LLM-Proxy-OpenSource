"""Tests for /proxy reverse proxy (PRXY-02, PRXY-03, PRXY-04–PRXY-06)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
from sqlalchemy import select
from starlette.testclient import TestClient

from app.api.deps import get_db, get_vault
from app.db.models import Binding, DbMetadata, Secret
from app.services.vault import VaultService


def _seed_secret_and_binding(client) -> None:
    assert (
        client.post(
            "/api/secrets",
            json={
                "key": "secret.test.api",
                "value": "upstream-secret-token",
                "project_id": None,
                "base_url": "https://upstream.example",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/bindings",
            json={
                "service_name": "llm",
                "secret_ref_key": "secret.test.api",
                "project_id": None,
            },
        ).status_code
        == 201
    )


def test_proxy_streaming_post_forwards_sse_and_strips_authorization(client, app, monkeypatch):
    _seed_secret_and_binding(client)

    async def sse_chunks():
        yield b'data: {"id":1}\n\n'

    mock_upstream = MagicMock()
    mock_upstream.status_code = 200
    mock_upstream.headers = httpx.Headers(
        {
            "content-type": "text/event-stream",
            "Authorization": "should-not-leak",
        }
    )
    mock_upstream.aiter_bytes = sse_chunks
    mock_upstream.aread = AsyncMock(return_value=b"{}")
    mock_upstream.aclose = AsyncMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock(return_value="built-req")
    mock_client.send = AsyncMock(return_value=mock_upstream)
    mock_client.aclose = AsyncMock()

    app.state.httpx_client = mock_client

    r = client.post(
        "/proxy/llm/v1/chat/completions",
        json={"model": "x", "messages": [], "stream": True},
    )
    assert r.status_code == 200
    assert "text/event-stream" in (r.headers.get("content-type") or "").lower()
    assert "data:" in r.text
    assert all(k.lower() != "authorization" for k in r.headers.keys())
    mock_client.send.assert_called_once()


def test_proxy_happy_path_strips_upstream_authorization(client, app, monkeypatch):
    _seed_secret_and_binding(client)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"ok":true}'
    mock_resp.headers = httpx.Headers(
        {
            "content-type": "application/json",
            "Authorization": "should-not-leak",
        }
    )

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.aclose = AsyncMock()

    app.state.httpx_client = mock_client

    r = client.get("/proxy/llm/v1/models")
    assert r.status_code == 200
    assert r.json().get("ok") is True
    assert all(k.lower() != "authorization" for k in r.headers.keys())


def test_proxy_unknown_service_returns_binding_not_found(client):
    r = client.get("/proxy/unknown-service/v1/models")
    assert r.status_code == 404
    assert r.json()["code"] == "BINDING_NOT_FOUND"


def test_proxy_vault_locked(app, db_session):
    if db_session.scalar(select(DbMetadata).where(DbMetadata.id == 1)) is None:
        VaultService.create_new_database(db_session, "test-master-password")

    vault = VaultService()
    vault.unlock(db_session, "test-master-password")
    sid = str(uuid.uuid4())
    bid = str(uuid.uuid4())
    db_session.add(
        Secret(
            id=sid,
            key="secret.locked.proxy",
            value=vault.encrypt_secret_value("x"),
            enabled=True,
            base_url="https://upstream.example",
            project_id=None,
        )
    )
    db_session.add(
        Binding(
            id=bid,
            service_name="lockedsvc",
            secret_ref_key="secret.locked.proxy",
            project_id=None,
        )
    )
    db_session.commit()

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
            r = c.get("/proxy/lockedsvc/v1/models")
            assert r.status_code == 423
            assert r.json()["code"] == "VAULT_LOCKED"
    finally:
        app.dependency_overrides.clear()


def test_proxy_secret_disabled_returns_secret_disabled(client):
    _seed_secret_and_binding(client)
    sec_list = client.get("/api/secrets").json()["items"]
    row = next(x for x in sec_list if x["key"] == "secret.test.api")
    sid = row["id"]
    assert client.patch(f"/api/secrets/{sid}", json={"enabled": False}).status_code == 200

    r = client.get("/proxy/llm/v1/models")
    assert r.status_code == 403
    assert r.json()["code"] == "SECRET_DISABLED"


def test_proxy_missing_base_url_returns_validation_error(client):
    assert (
        client.post(
            "/api/secrets",
            json={
                "key": "secret.no.baseurl.proxy",
                "value": "x",
                "project_id": None,
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/bindings",
            json={
                "service_name": "nobase",
                "secret_ref_key": "secret.no.baseurl.proxy",
                "project_id": None,
            },
        ).status_code
        == 201
    )
    r = client.get("/proxy/nobase/v1")
    assert r.status_code == 400
    assert r.json()["code"] == "VALIDATION_ERROR"
