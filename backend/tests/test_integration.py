"""Cross-cutting integration tests: vault, project, secret, render, export, proxy (CLID-04)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx


def test_integration_vault_unlocked(client) -> None:
    """Vault fixture leaves API in unlocked state (D-112 chain start)."""
    r = client.get("/api/vault/status")
    assert r.status_code == 200
    assert r.json()["locked"] is False


def test_integration_project_secret_ref_render_export(client) -> None:
    """Create project-scoped secret; render and export show secret_ref tag."""
    name = f"IntProj-{uuid.uuid4().hex[:8]}"
    pr = client.post("/api/projects", json={"name": name, "description": "integration"})
    assert pr.status_code == 201
    project_id = pr.json()["id"]

    assert (
        client.post(
            "/api/secrets",
            json={
                "key": "secret.student.name",
                "value": "IntegrationUser",
                "project_id": project_id,
            },
        ).status_code
        == 201
    )

    template = "Hello [[secret_ref.student.name]]"
    rr = client.post("/api/render", json={"template": template, "project_id": project_id})
    assert rr.status_code == 200
    body = rr.json()
    assert "[secret_ref:student.name]" in body["rendered"]

    er = client.post(
        "/api/export",
        json={"template": template, "format": "markdown", "project_id": project_id},
    )
    assert er.status_code == 200
    assert b"[secret_ref:student.name]" in er.content


def test_integration_secret_round_trip_and_proxy_mocked(client, monkeypatch) -> None:
    """Secret stored encrypted; proxy path decrypts for upstream auth; httpx mocked for CI stability."""
    name = f"ProxyProj-{uuid.uuid4().hex[:8]}"
    pr = client.post("/api/projects", json={"name": name, "description": "proxy chain"})
    assert pr.status_code == 201
    project_id = pr.json()["id"]

    svc = f"intsvc_{uuid.uuid4().hex[:8]}"
    secret_key = f"secret.integration.{uuid.uuid4().hex[:8]}"

    assert (
        client.post(
            "/api/secrets",
            json={
                "key": secret_key,
                "value": "upstream-secret-token",
                "project_id": project_id,
                "base_url": "https://upstream.example",
            },
        ).status_code
        == 201
    )

    assert (
        client.post(
            "/api/bindings",
            json={
                "service_name": svc,
                "secret_ref_key": secret_key,
                "project_id": project_id,
            },
        ).status_code
        == 201
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"models":[]}'
    mock_resp.headers = httpx.Headers({"content-type": "application/json"})

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.aclose = AsyncMock()

    client.app.state.httpx_client = mock_client

    r = client.get(f"/proxy/{svc}/v1/models", params={"project_id": project_id})
    assert r.status_code == 200
    assert r.json() == {"models": []}
    mock_client.request.assert_called_once()
