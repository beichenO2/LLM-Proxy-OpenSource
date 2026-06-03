"""Extended proxy tests — upstream errors, query forwarding, response sanitization (PRXY-07+)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx


def _seed(client) -> None:
    assert (
        client.post(
            "/api/secrets",
            json={
                "key": "secret.proxy.ext",
                "value": "my-upstream-token",
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
                "service_name": "ext",
                "secret_ref_key": "secret.proxy.ext",
                "project_id": None,
            },
        ).status_code
        == 201
    )


def _mock_non_streaming(app, **resp_overrides):
    """Set up a mock httpx client for non-streaming proxy requests."""
    resp = MagicMock()
    resp.status_code = resp_overrides.get("status_code", 200)
    resp.content = resp_overrides.get("content", b'{"ok":true}')
    resp.headers = httpx.Headers(resp_overrides.get("headers", {"content-type": "application/json"}))

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=resp)
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client
    return mock_client


def test_proxy_upstream_502_on_request_error(client, app):
    """httpx.RequestError during non-streaming request returns 502."""
    _seed(client)

    mock_client = MagicMock()
    mock_client.request = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client

    r = client.get("/proxy/ext/v1/models")
    assert r.status_code == 502
    data = r.json()
    assert data["ok"] is False
    assert "service" in data


def test_proxy_upstream_4xx_sanitized(client, app):
    """Upstream 4xx response body is returned with sanitized content."""
    _seed(client)
    _mock_non_streaming(
        app,
        status_code=422,
        content=b'{"error":"bad request with my-upstream-token"}',
    )

    r = client.get("/proxy/ext/v1/bad")
    assert r.status_code == 422
    data = r.json()
    assert data["ok"] is False
    assert "my-upstream-token" not in r.text


def test_proxy_query_string_forwarded(client, app):
    """Query parameters are forwarded to upstream."""
    _seed(client)
    mock_client = _mock_non_streaming(app)

    r = client.get("/proxy/ext/v1/models?limit=10&offset=0")
    assert r.status_code == 200
    call_args = mock_client.request.call_args
    called_url = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("url", "")
    assert "limit=10" in called_url
    assert "offset=0" in called_url


def test_proxy_post_non_streaming_forwards_body(client, app):
    """POST without stream=true uses non-streaming path."""
    _seed(client)
    mock_client = _mock_non_streaming(app)

    r = client.post(
        "/proxy/ext/v1/chat/completions",
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200
    call_args = mock_client.request.call_args
    assert call_args.args[0] == "POST"


def test_proxy_streaming_upstream_error_returns_502(client, app):
    """Streaming path: httpx.RequestError -> 502."""
    _seed(client)

    mock_client = MagicMock()
    mock_client.build_request = MagicMock(return_value="built-req")
    mock_client.send = AsyncMock(side_effect=httpx.ConnectError("timeout"))
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client

    r = client.post(
        "/proxy/ext/v1/chat/completions",
        json={"model": "x", "messages": [], "stream": True},
    )
    assert r.status_code == 502
    data = r.json()
    assert data["ok"] is False
    assert "service" in data


def test_proxy_streaming_upstream_4xx_returns_error_response(client, app):
    """Streaming path: upstream 4xx -> structured error with suggestion."""
    _seed(client)

    mock_upstream = MagicMock()
    mock_upstream.status_code = 429
    mock_upstream.headers = httpx.Headers({"content-type": "application/json"})
    mock_upstream.aread = AsyncMock(return_value=b'{"error":"rate limited"}')
    mock_upstream.aclose = AsyncMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock(return_value="built-req")
    mock_client.send = AsyncMock(return_value=mock_upstream)
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client

    r = client.post(
        "/proxy/ext/v1/chat/completions",
        json={"model": "x", "messages": [], "stream": True},
    )
    assert r.status_code == 429
    data = r.json()
    assert data["ok"] is False
    assert "rate limited" in data["error"]
    assert data["suggestion"]
    assert data.get("retry_after_seconds") == 60


def test_proxy_path_empty_uses_base_url_directly(client, app):
    """When path is empty, upstream URL is just the base_url."""
    _seed(client)
    mock_client = _mock_non_streaming(app)

    r = client.get("/proxy/ext/")
    assert r.status_code == 200
    call_args = mock_client.request.call_args
    called_url = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("url", "")
    assert called_url == "https://upstream.example"


def test_proxy_binding_exists_but_secret_missing(client):
    """Binding references a secret key whose secret has been deleted -> 404."""
    r = client.post("/api/secrets", json={
        "key": "secret.will.delete",
        "value": "temp",
        "project_id": None,
        "base_url": "https://example.com",
    })
    assert r.status_code == 201
    sid = r.json()["id"]

    r = client.post("/api/bindings", json={
        "service_name": "orphan-svc",
        "secret_ref_key": "secret.will.delete",
        "project_id": None,
    })
    assert r.status_code == 201

    r = client.delete(f"/api/secrets/{sid}")
    assert r.status_code == 204

    r = client.get("/proxy/orphan-svc/v1/test")
    assert r.status_code == 404


def test_proxy_post_invalid_json_body_no_streaming(client, app):
    """POST with invalid JSON body defaults to non-streaming."""
    _seed(client)
    mock_client = _mock_non_streaming(app)

    r = client.post(
        "/proxy/ext/v1/chat/completions",
        content=b"this is not json at all",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 200
    call_args = mock_client.request.call_args
    assert call_args.args[0] == "POST"


def test_proxy_sse_media_type_non_sse(client, app):
    """When upstream content-type is NOT text/event-stream, default SSE type is used."""
    _seed(client)

    mock_upstream = MagicMock()
    mock_upstream.status_code = 200
    mock_upstream.headers = httpx.Headers({"content-type": "application/octet-stream"})

    async def aiter_bytes():
        yield b"data: hello\n\n"

    mock_upstream.aiter_bytes = aiter_bytes
    mock_upstream.aclose = AsyncMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock(return_value="built-req")
    mock_client.send = AsyncMock(return_value=mock_upstream)
    mock_client.aclose = AsyncMock()
    app.state.httpx_client = mock_client

    r = client.post(
        "/proxy/ext/v1/chat/completions",
        json={"model": "x", "messages": [], "stream": True},
    )
    assert r.status_code == 200


def test_proxy_with_custom_auth_header_binding(client, app):
    """Binding with custom auth_header sends the secret via that header."""
    assert (
        client.post(
            "/api/secrets",
            json={
                "key": "secret.custom.auth",
                "value": "custom-token-value",
                "project_id": None,
                "base_url": "https://custom.example",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/bindings",
            json={
                "service_name": "custom-auth-svc",
                "secret_ref_key": "secret.custom.auth",
                "project_id": None,
                "auth_header": "X-Api-Key",
            },
        ).status_code
        == 201
    )

    mock_client = _mock_non_streaming(app)

    r = client.get("/proxy/custom-auth-svc/v1/test")
    assert r.status_code == 200
    call_kwargs = mock_client.request.call_args.kwargs
    sent_headers = call_kwargs.get("headers", {})
    assert "X-Api-Key" in sent_headers
    assert sent_headers["X-Api-Key"] == "custom-token-value"
