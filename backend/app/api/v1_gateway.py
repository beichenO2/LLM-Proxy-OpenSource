"""Unified LLM gateway — /v1/chat/completions and /v1/models.

This layer provides a single OpenAI-compatible entry point.
Callers only need to specify a model name; the gateway resolves the
correct upstream binding automatically via model_routing.MODEL_ROUTING.

Usage (any OpenAI-compatible SDK):
    client = OpenAI(
        base_url="http://127.0.0.1:12790/v1",
        api_key="local",   # ignored — PolarPrivate handles auth
    )
    client.chat.completions.create(model="001", ...)  # → MiniMax-M3 (fast)
    client.chat.completions.create(model="qwen3-coder-plus", ...)

The /proxy/* routes are untouched and remain fully functional.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response, StreamingResponse

from app.api.deps import get_db, get_vault
from app.api.proxy import (
    _NON_STREAM_TIMEOUT,
    _STREAM_TIMEOUT,
    _filter_response_headers,
    _outgoing_auth_header,
    _sanitize_upstream_body,
    _sse_media_type,
    _wrap_upstream_error,
    _check_and_truncate_prompt,
    _record_usage,
    _update_service_status,
    _SKIP_REQUEST_HEADERS,
)
from app.core.model_catalog import MODEL_CATALOG
from app.core.cursor_cli_routing import CURSOR_SERVICE_NAME, cursor_cli_available
from app.core.local_model_routing import (
    EMBED_CODE,
    LOCAL_SERVICE_NAME,
    normalize_embed_code,
    ollama_base_url,
    resolve_ollama_embed_model,
    resolve_ollama_chat_model,
)
from app.core.model_routing import (
    caller_facing_model,
    get_load_balance_group,
    is_opaque_caller_model,
    select_service_by_weight,
    resolve_model_and_service,
)
from app.db.models import Binding, Secret
from app.logging_config import get_logger
from app.services.cursor_cli_adapter import (
    CursorCliError,
    CursorCliTimeout,
    chat_completion as cursor_chat_completion,
)
from app.services.minimax_gateway import apply_minimax_upstream_defaults
from app.services.vault import VaultService

router = APIRouter(tags=["v1-gateway"])
_LOG = get_logger(__name__)


# ── /v1/models ──────────────────────────────────────────────────────────────

@router.get("/models")
def list_models(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
) -> dict:
    """List all known models available through the PolarPrivate proxy.

    SDK callers (PolarUI, scripts) only need vault unlocked — no browser session cookie.
    """
    if not vault.is_unlocked:
        raise HTTPException(
            status_code=423,
            detail={"detail": "Vault is locked", "code": "VAULT_LOCKED"},
        )
    # Collect resolved service names
    bindings = session.scalars(select(Binding)).all()
    secrets_by_key: dict[str, Secret] = {
        s.key: s for s in session.scalars(select(Secret)).all()
    }
    resolved_services: set[str] = set()
    for b in bindings:
        sec = secrets_by_key.get(b.secret_ref_key)
        if sec and sec.enabled and b.project_id is None:
            resolved_services.add(b.service_name)

    now = int(time.time())
    data = []
    for entry in MODEL_CATALOG:
        if entry.service == CURSOR_SERVICE_NAME:
            if not cursor_cli_available():
                continue
        elif entry.service != LOCAL_SERVICE_NAME and entry.service not in resolved_services:
            continue
        data.append({
            "id": entry.id,
            "object": "model",
            "created": now,
            "owned_by": entry.provider,
            "service": entry.service,
            "description": entry.description,
        })

    return {
        "object": "list",
        "data": data,
        "hint": (
            "Pass any model id to POST /v1/chat/completions. "
            "PolarPrivate routes to the correct upstream automatically."
        ),
    }


# ── /v1/chat/completions ─────────────────────────────────────────────────────

def _get_shared_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.httpx_client


def _resolve_binding_and_secret(
    session: Session,
    service_name: str,
) -> tuple[Binding, Secret, str] | None:
    """Return (binding, secret, plaintext) or None if not found/disabled."""
    binding = session.scalars(
        select(Binding)
        .where(Binding.service_name == service_name, Binding.project_id.is_(None))
    ).first()
    if binding is None:
        return None

    secret = session.scalars(
        select(Secret)
        .where(Secret.key == binding.secret_ref_key, Secret.project_id.is_(None))
    ).first()
    if secret is None or not secret.enabled:
        return None

    return binding, secret, ""  # plaintext filled below


@router.post("/embeddings")
async def unified_embeddings(
    request: Request,
) -> Response:
    """Forward embeddings using opaque code E000 (one embedding model slot)."""
    body = await request.body()
    try:
        obj = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail={
            "detail": "Request body must be valid JSON",
            "code": "INVALID_JSON",
        })

    caller_model = str(obj.get("model", EMBED_CODE)).strip()
    embed_code = normalize_embed_code(caller_model)
    if not embed_code:
        raise HTTPException(status_code=422, detail={
            "detail": f"Embedding model must be {EMBED_CODE}.",
            "code": "UNKNOWN_MODEL",
        })

    obj["model"] = resolve_ollama_embed_model(embed_code)
    body = json.dumps(obj).encode("utf-8")
    upstream_url = f"{ollama_base_url()}/v1/embeddings"

    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _SKIP_REQUEST_HEADERS and k.lower() != "authorization"
    }
    forward_headers["content-type"] = "application/json"

    client = _get_shared_client(request)
    try:
        resp = await client.request(
            "POST", upstream_url,
            headers=forward_headers,
            content=body,
            timeout=_NON_STREAM_TIMEOUT,
        )
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "Ollama embeddings timed out"})
    except httpx.RequestError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})

    if resp.status_code >= 400:
        return _wrap_upstream_error(resp.status_code, resp.content, "", LOCAL_SERVICE_NAME,
                                    upstream_headers=resp.headers)

    out = _rewrite_response_model(resp.content, embed_code)
    return Response(content=out, status_code=resp.status_code,
                    headers=_filter_response_headers(resp.headers))


def _rewrite_response_model(body: bytes, caller_model: str) -> bytes:
    """Strip upstream model names from JSON responses; echo capability / L-code."""
    try:
        obj = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body
    if isinstance(obj, dict) and "model" in obj:
        obj["model"] = caller_facing_model(caller_model, str(obj.get("model", "")))
        return json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return body


async def _forward_cursor_cli(
    caller_model: str,
    obj: dict,
) -> Response:
    """Invoke Cursor Agent CLI and return an OpenAI-compatible JSON response."""
    messages = obj.get("messages")
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=422, detail={
            "detail": "Field 'messages' must be a non-empty array",
            "code": "VALIDATION_ERROR",
        })

    if obj.get("stream") is True:
        raise HTTPException(status_code=422, detail={
            "detail": "Cursor CLI proxy does not support streaming yet.",
            "code": "STREAM_NOT_SUPPORTED",
            "hint": "Set stream=false or use a cloud/local Ollama model.",
        })

    if not cursor_cli_available():
        return JSONResponse(status_code=503, content={
            "ok": False,
            "error": "Cursor Agent CLI not found",
            "service": CURSOR_SERVICE_NAME,
            "model": caller_model,
            "hint": "Install Cursor CLI (`agent`) and run `agent login`.",
        })

    _LOG.info("v1_gateway_cursor_cli", caller_model=caller_model)
    try:
        payload = await cursor_chat_completion(
            caller_model=caller_model,
            messages=messages,
        )
    except CursorCliTimeout as exc:
        return JSONResponse(status_code=504, content={
            "ok": False,
            "error": str(exc),
            "service": CURSOR_SERVICE_NAME,
            "model": caller_model,
            "hint": "Cursor CLI can be slow; increase CURSOR_AGENT_TIMEOUT if needed.",
        })
    except CursorCliError as exc:
        return JSONResponse(status_code=502, content={
            "ok": False,
            "error": str(exc),
            "service": CURSOR_SERVICE_NAME,
            "model": caller_model,
            "hint": "Run `agent login` and verify `agent status`.",
        })

    payload["model"] = caller_facing_model(caller_model, str(payload.get("model", "")))
    return JSONResponse(content=payload)


async def _forward_local_ollama(
    request: Request,
    client: httpx.AsyncClient,
    body: bytes,
    caller_model: str,
    obj: dict,
) -> Response:
    """Forward to Ollama OpenAI-compatible API; never expose Ollama model tags to callers."""
    ollama_model = resolve_ollama_chat_model(caller_model)
    obj["model"] = ollama_model
    body = json.dumps(obj).encode("utf-8")
    upstream_url = f"{ollama_base_url()}/v1/chat/completions"

    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in _SKIP_REQUEST_HEADERS and k.lower() != "authorization"
    }
    forward_headers["content-type"] = "application/json"

    use_streaming = obj.get("stream") is True
    _LOG.info("v1_gateway_local_ollama", caller_model=caller_model, stream=use_streaming)

    if use_streaming:
        return await _forward_v1_streaming(
            client, upstream_url, forward_headers, body,
            plaintext_secret="", service_name=LOCAL_SERVICE_NAME,
            caller_model=caller_model,
        )

    try:
        resp = await client.request(
            "POST", upstream_url,
            headers=forward_headers,
            content=body,
            timeout=_NON_STREAM_TIMEOUT,
        )
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={
            "ok": False,
            "error": "Ollama request timed out",
            "service": LOCAL_SERVICE_NAME,
            "model": caller_model,
        })
    except httpx.RequestError as exc:
        return JSONResponse(status_code=502, content={
            "ok": False,
            "error": str(exc),
            "service": LOCAL_SERVICE_NAME,
            "model": caller_model,
            "hint": "Ensure Ollama is running (ollama serve) and OLLAMA_URL is reachable.",
        })

    if resp.status_code >= 400:
        return _wrap_upstream_error(
            resp.status_code, resp.content, "", LOCAL_SERVICE_NAME,
            upstream_headers=resp.headers,
        )

    content = _rewrite_response_model(resp.content, caller_model)
    return Response(
        content=content,
        status_code=resp.status_code,
        headers=_filter_response_headers(resp.headers),
    )


@router.post("/chat/completions")
async def unified_chat_completions(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
) -> Response:
    """Route a chat completion request to the correct upstream binding by model name.

    The request body must be valid JSON with at least a ``model`` field.
    All other fields are forwarded as-is to the upstream OpenAI-compatible endpoint.
    """
    body = await request.body()

    # Parse body to extract model name
    try:
        obj = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail={
            "detail": "Request body must be valid JSON",
            "code": "INVALID_JSON",
        })

    model = obj.get("model", "")
    if not model:
        raise HTTPException(status_code=422, detail={
            "detail": "Field 'model' is required",
            "code": "VALIDATION_ERROR",
        })

    caller_model = str(model).strip()

    # Resolve service name and exact full model from alias
    full_model, service_name = resolve_model_and_service(caller_model)
    if service_name is None:
        raise HTTPException(status_code=422, detail={
            "detail": "Use cloud codes (000–111), local L000/L100/L101, Cursor C000, or E000 for embeddings.",
            "code": "UNKNOWN_MODEL",
            "hint": "Local: L000=8B, L100=32B, L101=VLM. Cursor: C000 or composer-2.5-fast. Cloud: 001 fast (MiniMax-M3); 100/110/111 retired → 001.",
        })

    if service_name == CURSOR_SERVICE_NAME:
        return await _forward_cursor_cli(full_model, obj)

    client = _get_shared_client(request)

    # Local Ollama — no vault / binding required
    if service_name == LOCAL_SERVICE_NAME:
        return await _forward_local_ollama(request, client, body, full_model, obj)

    if not vault.is_unlocked:
        raise HTTPException(
            status_code=423,
            detail={"detail": "Vault is locked", "code": "VAULT_LOCKED"},
        )

    # Load-balance override: if model has a multi-source group, pick by weight
    lb_group = get_load_balance_group(full_model)
    if lb_group:
        service_name = select_service_by_weight(lb_group)
        _LOG.info("load_balance_selected", model=full_model, service=service_name)

    # Overwrite the model field in the upstream payload to standard full name
    obj["model"] = full_model
    apply_minimax_upstream_defaults(obj)
    body = json.dumps(obj).encode("utf-8")
    opaque_response = is_opaque_caller_model(caller_model)

    # Look up binding + secret
    binding = session.scalars(
        select(Binding)
        .where(Binding.service_name == service_name, Binding.project_id.is_(None))
    ).first()
    if binding is None:
        raise HTTPException(status_code=503, detail={
            "detail": f"Binding '{service_name}' not configured for model '{model}'.",
            "code": "BINDING_NOT_FOUND",
            "hint": "Add the binding in PolarPrivate or check model_routing.py.",
        })

    secret = session.scalars(
        select(Secret)
        .where(Secret.key == binding.secret_ref_key, Secret.project_id.is_(None))
    ).first()
    if secret is None or not secret.enabled:
        raise HTTPException(status_code=503, detail={
            "detail": f"Secret for binding '{service_name}' is missing or disabled.",
            "code": "SECRET_UNAVAILABLE",
        })

    raw_base = (secret.base_url or "").strip()
    if not raw_base:
        raise HTTPException(status_code=503, detail={
            "detail": f"No base_url configured for binding '{service_name}'.",
            "code": "MISSING_BASE_URL",
        })

    plaintext = vault.decrypt_secret_value(secret.value)
    auth_extra = _outgoing_auth_header(binding, plaintext)

    # Build upstream URL
    base = raw_base.rstrip("/")
    upstream_url = f"{base}/chat/completions"

    # Forward headers (strip hop-by-hop, inject auth)
    forward_headers: dict[str, str] = {}
    for key, value in request.headers.items():
        if key.lower() in _SKIP_REQUEST_HEADERS:
            continue
        if key.lower() == "authorization":
            continue  # Replace with real auth
        forward_headers[key] = value
    forward_headers.update(auth_extra)

    # Auto-truncate prompt if too long
    body, was_truncated = _check_and_truncate_prompt(body)
    if was_truncated:
        _LOG.info("v1_gateway_prompt_truncated", service=service_name, model=model)

    use_streaming = obj.get("stream") is True

    _LOG.info("v1_gateway_route", model=caller_model, service=service_name, stream=use_streaming)

    if use_streaming:
        return await _forward_v1_streaming(
            client, upstream_url, forward_headers, body,
            plaintext_secret=plaintext, service_name=service_name,
            caller_model=caller_model if opaque_response else "",
        )

    # Non-streaming
    try:
        resp = await client.request(
            "POST", upstream_url,
            headers=forward_headers,
            content=body,
            timeout=_NON_STREAM_TIMEOUT,
        )
    except httpx.TimeoutException:
        _record_usage(session, service_name, None, is_error=True)
        _update_service_status(session, service_name, is_error=True, error_message="Timeout")
        return JSONResponse(status_code=504, content={
            "ok": False,
            "error": "Upstream LLM request timed out (300s limit)",
            "service": service_name,
            "model": model,
            "suggestion": "Try a shorter prompt or a faster model.",
        })
    except httpx.RequestError as exc:
        _record_usage(session, service_name, None, is_error=True)
        _update_service_status(session, service_name, is_error=True, error_message=str(exc)[:500])
        return JSONResponse(status_code=502, content={
            "ok": False,
            "error": str(exc),
            "service": service_name,
            "model": model,
            "suggestion": "Cannot connect to upstream. Verify PolarPrivate binding.",
        })

    is_error = resp.status_code >= 400
    _record_usage(session, service_name, None, is_error=is_error)
    _update_service_status(session, service_name, is_error=is_error, error_message=None if not is_error else f"HTTP {resp.status_code}")

    if is_error:
        # Auto-retry on 5xx with exponential backoff (up to 3 attempts)
        if resp.status_code in (500, 502, 503):
            import asyncio
            _RETRY_DELAYS = [1.0, 3.0, 7.0]
            for attempt, delay in enumerate(_RETRY_DELAYS, 1):
                _LOG.warning("v1_gateway_auto_retry", service=service_name, status=resp.status_code, attempt=attempt, delay_s=delay)
                await asyncio.sleep(delay)
                try:
                    retry_resp = await client.request(
                        "POST", upstream_url,
                        headers=forward_headers,
                        content=body,
                        timeout=_NON_STREAM_TIMEOUT,
                    )
                    if retry_resp.status_code < 400:
                        _record_usage(session, service_name, None, is_error=False)
                        _update_service_status(session, service_name, is_error=False)
                        retry_body = retry_resp.content
                        if opaque_response:
                            retry_body = _rewrite_response_model(retry_body, caller_model)
                        return Response(
                            content=retry_body,
                            status_code=retry_resp.status_code,
                            headers=_filter_response_headers(retry_resp.headers),
                        )
                    resp = retry_resp
                    if resp.status_code not in (500, 502, 503):
                        break
                except httpx.RequestError:
                    if attempt == len(_RETRY_DELAYS):
                        break
                    continue
        return _wrap_upstream_error(resp.status_code, resp.content, plaintext, service_name,
                                    upstream_headers=resp.headers)

    out_body = resp.content
    if opaque_response:
        out_body = _rewrite_response_model(out_body, caller_model)

    return Response(
        content=out_body,
        status_code=resp.status_code,
        headers=_filter_response_headers(resp.headers),
    )


async def _forward_v1_streaming(
    client: httpx.AsyncClient,
    upstream_url: str,
    forward_headers: dict[str, str],
    body: bytes,
    plaintext_secret: str = "",
    service_name: str = "",
    caller_model: str = "",
) -> Response:
    """Streaming forward for /v1/chat/completions."""
    try:
        req = client.build_request(
            "POST", upstream_url,
            headers=forward_headers,
            content=body,
            timeout=_STREAM_TIMEOUT,
        )
        upstream = await client.send(req, stream=True)
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={
            "ok": False,
            "error": "Upstream streaming request timed out",
            "service": service_name,
            "suggestion": "Try a shorter prompt or disable streaming.",
        })
    except httpx.RequestError as exc:
        return JSONResponse(status_code=502, content={
            "ok": False,
            "error": str(exc),
            "service": service_name,
        })

    if upstream.status_code >= 400:
        try:
            err_body = await upstream.aread()
        finally:
            await upstream.aclose()
        return _wrap_upstream_error(upstream.status_code, err_body, plaintext_secret, service_name,
                                    upstream_headers=upstream.headers)

    media = _sse_media_type(upstream)
    resp_headers = _filter_response_headers(upstream.headers)
    status = upstream.status_code

    async def aiter_stream() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield _sanitize_upstream_body(chunk, plaintext_secret) if plaintext_secret else chunk
        finally:
            await upstream.aclose()

    return StreamingResponse(
        aiter_stream(),
        status_code=status,
        headers=resp_headers,
        media_type=media,
    )
