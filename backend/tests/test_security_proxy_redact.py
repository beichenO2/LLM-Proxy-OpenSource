"""Security tests: proxy error responses must never leak injected secrets."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx


def _seed(client) -> None:
    assert (
        client.post(
            "/api/secrets",
            json={
                "key": "secret.redact.test",
                "value": "sk-SUPERSECRETVALUE12345678",
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
                "service_name": "redactsvc",
                "secret_ref_key": "secret.redact.test",
                "project_id": None,
            },
        ).status_code
        == 201
    )


def test_proxy_upstream_4xx_body_redacts_secret(client, app):
    """If upstream echoes back the API key in a 401 error body, it must be scrubbed."""
    _seed(client)

    leaked = "Your API key sk-SUPERSECRETVALUE12345678 is invalid"
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.content = leaked.encode()
    mock_resp.headers = httpx.Headers({"content-type": "application/json"})

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client

    r = client.get("/proxy/redactsvc/v1/models")
    assert r.status_code == 401
    assert "sk-SUPERSECRETVALUE12345678" not in r.text
    assert "[REDACTED]" in r.text


def test_proxy_httpx_error_redacts_secret(client, app):
    """httpx RequestError string representation must be sanitized."""
    _seed(client)

    mock_client = MagicMock()
    mock_client.request = AsyncMock(
        side_effect=httpx.ConnectError(
            "Connection to upstream.example failed with key sk-SUPERSECRETVALUE12345678"
        )
    )
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client

    r = client.get("/proxy/redactsvc/v1/models")
    assert r.status_code == 502
    assert "sk-SUPERSECRETVALUE12345678" not in r.text
    assert "[REDACTED]" in r.text


def test_proxy_streaming_4xx_redacts_secret(client, app):
    """Streaming path upstream 4xx error body must also be sanitized."""
    _seed(client)

    leaked_body = b'{"error":"invalid key sk-SUPERSECRETVALUE12345678"}'
    mock_upstream = MagicMock()
    mock_upstream.status_code = 403
    mock_upstream.headers = httpx.Headers({"content-type": "application/json"})
    mock_upstream.aread = AsyncMock(return_value=leaked_body)
    mock_upstream.aclose = AsyncMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock(return_value="built-req")
    mock_client.send = AsyncMock(return_value=mock_upstream)
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client

    r = client.post(
        "/proxy/redactsvc/v1/chat/completions",
        json={"model": "x", "messages": [], "stream": True},
    )
    assert r.status_code == 403
    assert "sk-SUPERSECRETVALUE12345678" not in r.text
    assert "[REDACTED]" in r.text


def test_unhandled_exception_does_not_leak_details(client):
    """Unknown API routes must not leak internal details."""
    r = client.get("/api/this-does-not-exist-at-all")
    assert r.status_code in (200, 404, 405)
    body = r.text
    assert "traceback" not in body.lower()
