"""Reverse proxy: binding resolution, vault decrypt, httpx forward (D-63–D-65, D-66–D-71).

Uses the shared httpx.AsyncClient from app.state.httpx_client (created in lifespan).
proxy=None bypasses system/Clash proxies to prevent freeze when the local proxy is down.

R8 enhancements (2026-04-26):
- Prompt length guard: estimate tokens, truncate if over threshold
  (hardcoded half-context caps for routed models; unknown models uncapped).
- Optionally strip OpenAI output caps max_tokens/max_completion_tokens (set PRIVPORTAL_FORWARD_MAX_TOKENS to keep client caps).
- Extended timeouts: non-streaming 300s read, streaming 180s read
- Structured upstream error wrapping with retry suggestions

R10 enhancements (2026-05-10):
- Fallback chain: when primary binding fails (429/5xx), automatically try fallback bindings
- Multi-key rotation: supports multiple API keys for the same service
- Cooldown mechanism: failed bindings are temporarily excluded from fallback chain
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse, Response, StreamingResponse

from app.api.deps import get_db, require_unlocked_vault
from app.core.config import Settings
from app.db.models import Binding, LLMServiceStatus, ProxyUsage, Secret
from app.logging_config import get_logger, sanitize_user_facing_string
from app.services.models_dev_limits import input_token_threshold_for_model
from app.services.vault import VaultService

router = APIRouter(tags=["proxy"])

_LOG = get_logger(__name__)

_SKIP_REQUEST_HEADERS = frozenset({
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "upgrade",
})


def _outgoing_auth_header(binding: Binding, plaintext: str) -> dict[str, str]:
    ah = binding.auth_header
    if ah is None or ah.strip().lower() == "authorization":
        return {"Authorization": f"Bearer {plaintext}"}
    return {ah: plaintext}


_SKIP_RESPONSE_HEADERS = frozenset({
    "authorization",
    "transfer-encoding",
    "content-encoding",
    "content-length",
    "connection",
    "keep-alive",
})


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _SKIP_RESPONSE_HEADERS}


def _sse_media_type(upstream: httpx.Response) -> str:
    ct = upstream.headers.get("content-type") or ""
    if "text/event-stream" in ct.lower():
        return ct.split(";")[0].strip()
    return "text/event-stream"


def _sanitize_upstream_body(body: bytes, plaintext: str) -> bytes:
    """Strip injected secret from upstream response body to prevent leak-back."""
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return body
    if plaintext and plaintext in text:
        text = text.replace(plaintext, "[REDACTED]")
    text = sanitize_user_facing_string(text)
    return text.encode("utf-8")


def _sanitize_error_detail(raw: str, plaintext: str) -> str:
    """Remove secret material from httpx exception messages."""
    if plaintext and plaintext in raw:
        raw = raw.replace(plaintext, "[REDACTED]")
    return sanitize_user_facing_string(raw)


_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
_NON_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)

_CHARS_PER_TOKEN = 3.5  # conservative for mixed CJK + English

_SECURITY_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "security-baseline.md"
_SECURITY_PROMPT: str | None = None


def _load_security_prompt() -> str:
    global _SECURITY_PROMPT
    if _SECURITY_PROMPT is None:
        try:
            _SECURITY_PROMPT = _SECURITY_PROMPT_PATH.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            _SECURITY_PROMPT = ""
            _LOG.warning("security_prompt_missing", path=str(_SECURITY_PROMPT_PATH))
    return _SECURITY_PROMPT


def _is_llm_service(service_name: str) -> bool:
    return service_name.startswith("llm.")


def _inject_system_prompts(
    obj: dict[str, Any],
    append_prompt: str | None,
) -> None:
    """Inject append_system_prompt and security baseline into messages.

    Order: original messages → caller's append prompt → security baseline (last).
    """
    messages = obj.get("messages")
    if not isinstance(messages, list):
        return

    if append_prompt:
        messages.append({"role": "system", "content": append_prompt})

    security = _load_security_prompt()
    if security:
        messages.append({"role": "system", "content": security})


def _forward_max_tokens_passthrough_enabled() -> bool:
    v = os.environ.get("PRIVPORTAL_FORWARD_MAX_TOKENS", "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _strip_openai_output_token_caps(obj: dict[str, Any]) -> None:
    """Remove client output caps so upstream can use full model defaults (unless opted in)."""
    if _forward_max_tokens_passthrough_enabled():
        return
    for key in ("max_tokens", "max_completion_tokens"):
        obj.pop(key, None)


def _estimate_content_chars(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        chars = 0
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                t = part.get("text") or ""
                if isinstance(t, str):
                    chars += len(t)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                chars += len(part["text"])
            elif isinstance(part, dict):
                chars += 128
            elif isinstance(part, str):
                chars += len(part)
            else:
                chars += len(str(part))
        return chars
    if content is None:
        return 0
    return len(str(content))


def _messages_estimated_tokens(messages: list[Any]) -> int:
    chars = sum(
        _estimate_content_chars(m.get("content") if isinstance(m, dict) else None)
        for m in messages
    )
    return int(chars / _CHARS_PER_TOKEN)


def _maybe_truncate_messages(obj: dict[str, Any], max_tokens_estimate: int) -> bool:
    """Truncation is disabled. Never truncate any prompt under any circumstance."""
    return False


def _prepare_chat_proxy_body(body: bytes) -> tuple[bytes, bool]:
    """Normalize OpenAI-style chat payloads: optional output-cap removal + input truncation."""
    truncated = False
    try:
        obj = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body, truncated

    if not isinstance(obj, dict) or "messages" not in obj:
        return body, truncated

    _strip_openai_output_token_caps(obj)
    raw_model = obj.get("model")
    model_hint = raw_model.strip() if isinstance(raw_model, str) else None
    threshold = input_token_threshold_for_model(model_hint)
    if threshold is not None:
        truncated = _maybe_truncate_messages(obj, threshold)
    return json.dumps(obj, ensure_ascii=False).encode("utf-8"), truncated


def _check_and_truncate_prompt(body: bytes) -> tuple[bytes, bool]:
    """Backward-compatible alias for tests and older imports."""
    return _prepare_chat_proxy_body(body)


_DEFAULT_RETRY_AFTER = int(os.environ.get("PRIVPORTAL_RETRY_AFTER", "60"))

# Fallback chain configuration
_FALLBACK_COOLDOWN_429 = int(os.environ.get("PRIVPORTAL_FALLBACK_COOLDOWN_429", "60"))
_FALLBACK_COOLDOWN_5XX = int(os.environ.get("PRIVPORTAL_FALLBACK_COOLDOWN_5XX", "30"))
_MAX_FALLBACK_ATTEMPTS = int(os.environ.get("PRIVPORTAL_MAX_FALLBACK_ATTEMPTS", "5"))


def _is_cooling_down(binding: Binding) -> bool:
    """Check if binding is in cooldown period (temporarily unavailable for fallback)."""
    if binding.cooldown_until is None:
        return False
    return binding.cooldown_until > datetime.utcnow()


def _set_binding_cooldown(binding: Binding, seconds: int) -> None:
    """Put binding into cooldown for specified seconds."""
    binding.cooldown_until = datetime.utcnow() + timedelta(seconds=seconds)
    binding.consecutive_failures += 1


def _reset_binding_failure_state(binding: Binding) -> None:
    """Reset cooldown and failure count after successful request."""
    binding.cooldown_until = None
    binding.consecutive_failures = 0


def _resolve_fallback_chain(session: Session, primary_binding: Binding) -> list[Binding]:
    """Resolve fallback chain from primary binding.

    Returns list of bindings to try (including primary), excluding those in cooldown.
    """
    chain = [primary_binding]

    if not primary_binding.fallback_chain:
        return chain

    try:
        fallback_names = json.loads(primary_binding.fallback_chain)
        if not isinstance(fallback_names, list):
            return chain
    except (json.JSONDecodeError, TypeError):
        return chain

    for name in fallback_names[:_MAX_FALLBACK_ATTEMPTS - 1]:
        if not isinstance(name, str):
            continue
        fb_binding = session.scalars(
            select(Binding).where(Binding.service_name == name)
        ).first()
        if fb_binding and not _is_cooling_down(fb_binding):
            chain.append(fb_binding)

    return chain


def _should_trigger_fallback(status_code: int) -> bool:
    """Determine if error status code should trigger fallback chain."""
    return status_code in (429, 500, 502, 503, 504)


def _wrap_upstream_error(
    status_code: int,
    body: bytes,
    plaintext: str,
    service_name: str,
    upstream_headers: httpx.Headers | dict[str, str] | None = None,
) -> JSONResponse:
    """Parse upstream LLM error and return a structured, actionable response."""
    sanitized_body = _sanitize_upstream_body(body, plaintext)
    upstream_msg = ""
    upstream_code = ""
    try:
        err_obj = json.loads(sanitized_body)
        err_inner = err_obj.get("error", err_obj)
        if isinstance(err_inner, dict):
            upstream_msg = err_inner.get("message", "")
            upstream_code = err_inner.get("code", err_inner.get("type", ""))
        elif isinstance(err_inner, str):
            upstream_msg = err_inner
    except (json.JSONDecodeError, UnicodeDecodeError):
        upstream_msg = sanitized_body.decode("utf-8", errors="replace")[:500]

    suggestion = ""
    retry_after = None

    if status_code == 429:
        if upstream_headers:
            raw_ra = (upstream_headers.get("retry-after") or "").strip()
            if raw_ra:
                try:
                    retry_after = int(raw_ra)
                except ValueError:
                    retry_after = None
        if retry_after is None:
            retry_after = _DEFAULT_RETRY_AFTER
        suggestion = f"Rate limited by upstream. Wait {retry_after}s and retry."
    elif status_code in (413, 400) and any(
        kw in upstream_msg.lower() for kw in ("token", "length", "too long", "too large", "maximum context")
    ):
        suggestion = "Prompt exceeds upstream model limit. Reduce message count or content length."
    elif status_code in (500, 502, 503):
        suggestion = "Upstream LLM service error. Will auto-retry once. If persistent, check service status."
    elif status_code == 401:
        suggestion = "Authentication failed. Check the Secret/Binding configuration in PolarPrivate."
    elif status_code == 502:
        # 区分 502 的具体类型
        err_lower = upstream_msg.lower()
        if any(kw in err_lower for kw in ["disconnect", "connection reset", "econnrefused", "econnreset", "network", "no response", "empty response", "server disconnected"]):
            suggestion = "Upstream server disconnected. This is a network-level issue - the server closed the connection before responding. Check if the upstream service is running or switch to a fallback provider."
        elif "timeout" in err_lower:
            suggestion = "Upstream timed out (HTTP 502). The server took too long to respond. Try a faster model or reduce prompt length."
        else:
            suggestion = "Upstream returned 502 Bad Gateway. The server received an invalid response from upstream. Will auto-retry once."
    else:
        suggestion = "Upstream returned an error. Check the error details."

    resp_body: dict = {
        "ok": False,
        "error": upstream_msg or f"upstream returned {status_code}",
        "upstream_status": status_code,
        "upstream_code": upstream_code,
        "service": service_name,
        "suggestion": suggestion,
    }

    headers: dict[str, str] = {}
    if retry_after:
        headers["Retry-After"] = str(retry_after)
        resp_body["retry_after_seconds"] = retry_after

    return JSONResponse(content=resp_body, status_code=status_code, headers=headers)


def _get_shared_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.httpx_client


async def _forward_streaming(
    client: httpx.AsyncClient,
    method: str,
    upstream_url: str,
    forward_headers: dict[str, str],
    body: bytes,
    plaintext_secret: str = "",
    service_name: str = "",
) -> Response:
    """Forward with httpx streaming using the shared client."""
    try:
        req = client.build_request(
            method, upstream_url, headers=forward_headers, content=body,
            timeout=_STREAM_TIMEOUT,
        )
        upstream = await client.send(req, stream=True)
    except httpx.TimeoutException as exc:
        _LOG.error("proxy_timeout", service=service_name, upstream_url=upstream_url, error=str(exc))
        err_str = str(exc).lower()
        if "connect" in err_str or "connection" in err_str:
            suggestion = "Connection timeout - upstream server did not respond in time. Check network connectivity or switch to a faster model."
        elif "read" in err_str or "response" in err_str:
            suggestion = "Read timeout - upstream server started responding but did not finish in time. The model may be overloaded. Try a faster model or reduce prompt length."
        else:
            suggestion = "Upstream LLM request timed out. Try a shorter prompt or a faster model."
        return JSONResponse(
            status_code=504,
            content={
                "ok": False,
                "error": f"Upstream LLM request timed out: {exc}",
                "upstream_status": None,
                "service": service_name,
                "suggestion": suggestion,
            },
        )
    except httpx.RequestError as exc:
        _LOG.error("proxy_connect_error", service=service_name, error=str(exc))
        return JSONResponse(
            status_code=502,
            content={
                "ok": False,
                "error": _sanitize_error_detail(str(exc), plaintext_secret),
                "upstream_status": None,
                "service": service_name,
                "suggestion": "Cannot connect to upstream service. Verify the service is running.",
            },
        )

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


def _build_proxy_url(binding: Binding) -> str:
    url = f"/proxy/{binding.service_name}"
    if binding.project_id is not None:
        url += f"?project_id={binding.project_id}"
    return url


@router.get("/", include_in_schema=True)
def list_proxy_routes(
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> dict:
    """Discovery endpoint: list all available proxy routes with usage info."""
    bindings = session.scalars(select(Binding)).all()
    secrets = session.scalars(select(Secret)).all()
    secret_lookup: dict[tuple[str, str | None], Secret] = {}
    for s in secrets:
        secret_lookup[(s.key, s.project_id)] = s

    settings = Settings()
    host_port = f"http://{settings.api_host}:{settings.api_port}"

    routes = []
    for b in bindings:
        sec = secret_lookup.get((b.secret_ref_key, b.project_id))
        proxy_path = _build_proxy_url(b)
        routes.append({
            "service_name": b.service_name,
            "proxy_url": f"{host_port}{proxy_path}",
            "project_id": b.project_id,
            "resolved": sec is not None and sec.enabled and bool(sec.base_url),
            "category": sec.category if sec else None,
            "usage": f"curl -X POST {host_port}{proxy_path}/chat/completions "
                     f"-H 'Content-Type: application/json' "
                     f"-d '{{\"model\":\"...\",\"messages\":[...]}}'",
        })
    return {
        "hint": "Use proxy_url to send requests. PolarPrivate auto-injects auth credentials.",
        "warning": "Do NOT use upstream URLs directly (e.g. coding.dashscope.aliyuncs.com). Always use proxy_url.",
        "routes": routes,
    }


@router.get("/usage/stats")
def get_proxy_usage_stats(
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_unlocked_vault)],
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    """Get aggregated proxy usage statistics for the dashboard."""
    from datetime import date, timedelta

    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = session.query(ProxyUsage).filter(ProxyUsage.date >= cutoff).all()

    by_service: dict[str, dict] = {}
    daily_totals: dict[str, int] = {}

    for r in rows:
        if r.service_name not in by_service:
            by_service[r.service_name] = {"requests": 0, "errors": 0}
        by_service[r.service_name]["requests"] += r.request_count
        by_service[r.service_name]["errors"] += r.error_count
        daily_totals[r.date] = daily_totals.get(r.date, 0) + r.request_count

    return {
        "period_days": days,
        "total_requests": sum(d["requests"] for d in by_service.values()),
        "total_errors": sum(d["errors"] for d in by_service.values()),
        "by_service": by_service,
        "daily": dict(sorted(daily_totals.items())),
    }


def _available_binding_names(session: Session) -> list[str]:
    return list(session.scalars(select(Binding.service_name)).all())


class _ProxyContext:
    """Context object passed through fallback chain for a single request."""

    def __init__(
        self,
        request: Request,
        path: str,
        project_id: str | None,
        vault: VaultService,
        session: Session,
    ):
        self.request = request
        self.path = path
        self.project_id = project_id
        self.vault = vault
        self.session = session
        self.client = _get_shared_client(request)

        # Parsed request body (cached)
        self._body_content: bytes | None = None
        self._use_streaming = False
        self._is_chat_json = False
        self._append_prompt_body: str | None = None
        self._append_prompt_header = request.headers.get("x-append-system-prompt")

    async def _parse_body(self) -> None:
        """Parse request body once."""
        if self._body_content is not None:
            return

        if self.request.method.upper() not in ("GET", "HEAD"):
            self._body_content = await self.request.body()
        else:
            self._body_content = b""

        if (
            self.request.method.upper() == "POST"
            and self._body_content
            and "json" in (self.request.headers.get("content-type") or "").lower()
        ):
            try:
                obj = json.loads(self._body_content.decode("utf-8"))
                self._use_streaming = obj.get("stream") is True
                self._is_chat_json = "messages" in obj
                self._append_prompt_body = obj.pop("append_system_prompt", None)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

    async def get_prepared_content(self, service_name: str) -> bytes | None:
        """Get request content, prepared for forwarding."""
        await self._parse_body()

        content = self._body_content
        if not content:
            return content

        if self._is_chat_json:
            content, _ = _check_and_truncate_prompt(content)

        if self._is_chat_json and _is_llm_service(service_name) and content:
            try:
                body_obj = json.loads(content.decode("utf-8"))
                body_obj.pop("append_system_prompt", None)
                append_prompt = self._append_prompt_body or self._append_prompt_header
                _inject_system_prompts(body_obj, append_prompt)
                content = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        return content

    @property
    def use_streaming(self) -> bool:
        return self._use_streaming

    @property
    def is_chat_json(self) -> bool:
        return self._is_chat_json


async def _proxy_single_binding(
    ctx: _ProxyContext,
    binding: Binding,
) -> tuple[Response, Secret | None, str | None]:
    """Execute proxy request for a single binding.

    Returns (response, secret, plaintext) tuple.
    plaintext is returned for error sanitization purposes.
    """
    # Resolve secret
    sec_stmt = select(Secret).where(Secret.key == binding.secret_ref_key)
    if binding.project_id is None:
        sec_stmt = sec_stmt.where(Secret.project_id.is_(None))
    else:
        sec_stmt = sec_stmt.where(Secret.project_id == binding.project_id)
    secret = ctx.session.scalars(sec_stmt).first()

    if secret is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Binding not found", "code": "BINDING_NOT_FOUND"},
        )
    if not secret.enabled:
        raise HTTPException(
            status_code=403,
            detail={"detail": "Secret is disabled", "code": "SECRET_DISABLED"},
        )

    raw_base = (secret.base_url or "").strip()
    if not raw_base:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "base_url is required on the secret for proxy forwarding",
                "code": "VALIDATION_ERROR",
            },
        )

    base = raw_base.rstrip("/")
    upstream_path = f"{base}/{ctx.path}" if ctx.path else base
    if ctx.request.url.query:
        upstream_url = f"{upstream_path}?{ctx.request.url.query}"
    else:
        upstream_url = upstream_path

    parse_src = raw_base if "://" in raw_base else f"https://{raw_base}"
    parsed = urlparse(parse_src)
    upstream_host = parsed.netloc or ""

    plaintext = ctx.vault.decrypt_secret_value(secret.value)
    auth_extra = _outgoing_auth_header(binding, plaintext)

    forward_headers: dict[str, str] = {}
    for key, value in ctx.request.headers.items():
        if key.lower() in _SKIP_REQUEST_HEADERS or key.lower() == "x-append-system-prompt":
            continue
        forward_headers[key] = value
    forward_headers.update(auth_extra)

    content = await ctx.get_prepared_content(binding.service_name)

    _LOG.info(
        "proxy_forward",
        service_name=binding.service_name,
        project_id=ctx.project_id,
        upstream_host=upstream_host,
        method=ctx.request.method,
    )

    # Handle streaming
    if ctx.use_streaming:
        resp = await _forward_streaming(
            ctx.client,
            ctx.request.method,
            upstream_url,
            forward_headers,
            content or b"",
            plaintext_secret=plaintext,
            service_name=binding.service_name,
        )
        return resp, secret, plaintext

    # Non-streaming request
    try:
        resp = await ctx.client.request(
            ctx.request.method,
            upstream_url,
            headers=forward_headers,
            content=content,
            timeout=_NON_STREAM_TIMEOUT,
        )
    except httpx.TimeoutException as exc:
        _LOG.error("proxy_timeout", service=binding.service_name, upstream_url=upstream_url, error=str(exc))
        _record_usage(ctx.session, binding.service_name, ctx.project_id, is_error=True)
        _update_service_status(ctx.session, binding.service_name, is_error=True, error_message="Timeout")
        err_str = str(exc).lower()
        if "connect" in err_str or "connection" in err_str:
            suggestion = "Connection timeout - upstream server did not respond in time. Check network connectivity or switch to a faster model."
        elif "read" in err_str or "response" in err_str:
            suggestion = "Read timeout - upstream started responding but did not finish. The model may be overloaded. Try a faster model or reduce prompt length."
        else:
            suggestion = "Upstream LLM request timed out (300s limit). Try a shorter prompt or a faster model."
        return JSONResponse(
            status_code=504,
            content={
                "ok": False,
                "error": f"Upstream LLM request timed out: {exc}",
                "upstream_status": None,
                "service": binding.service_name,
                "suggestion": suggestion,
            },
        ), secret, plaintext
    except httpx.RequestError as exc:
        _LOG.error("proxy_connect_error", service=binding.service_name, error=str(exc))
        _record_usage(ctx.session, binding.service_name, ctx.project_id, is_error=True)
        _update_service_status(ctx.session, binding.service_name, is_error=True, error_message=_sanitize_error_detail(str(exc), plaintext)[:500])
        err_str = str(exc).lower()
        if any(kw in err_str for kw in ["disconnect", "connection reset", "econnrefused", "econnreset", "network", "no response", "empty response", "server disconnected"]):
            suggestion = "Upstream server disconnected (network error). This is transient - retry or switch to a fallback provider."
        elif "timeout" in err_str:
            suggestion = "Connection timeout to upstream. Check network connectivity or switch to a faster model."
        else:
            suggestion = "Cannot connect to upstream service. Verify the service is running or switch to a fallback provider."
        return JSONResponse(
            status_code=502,
            content={
                "ok": False,
                "error": _sanitize_error_detail(str(exc), plaintext),
                "upstream_status": None,
                "service": binding.service_name,
                "suggestion": suggestion,
            },
        ), secret, plaintext

    is_error = resp.status_code >= 400
    _record_usage(ctx.session, binding.service_name, ctx.project_id, is_error=is_error)
    _update_service_status(ctx.session, binding.service_name, is_error=is_error, error_message=None if not is_error else f"HTTP {resp.status_code}")

    if is_error:
        return _wrap_upstream_error(
            resp.status_code, resp.content, plaintext, binding.service_name,
            upstream_headers=resp.headers
        ), secret, plaintext

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=_filter_response_headers(resp.headers),
    ), secret, plaintext


@router.api_route(
    "/{service_name}/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_request(
    service_name: str,
    path: str,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
    project_id: str | None = Query(default=None),
) -> Response:
    """Resolve binding → secret → decrypt → inject auth header → forward to upstream.

    R10: Supports fallback chain - when primary binding fails (429/5xx),
    automatically try fallback bindings in order.
    """
    # Resolve primary binding
    stmt = select(Binding).where(Binding.service_name == service_name)
    if project_id is not None:
        stmt = stmt.where(Binding.project_id == project_id)
    else:
        stmt = stmt.where(Binding.project_id.is_(None))
    primary_binding = session.scalars(stmt).first()
    if primary_binding is None:
        available = _available_binding_names(session)
        raise HTTPException(
            status_code=404,
            detail={
                "detail": f"Binding '{service_name}' not found",
                "code": "BINDING_NOT_FOUND",
                "available_bindings": available,
                "hint": "Use GET /proxy/ to discover all available routes",
            },
        )

    # Build fallback chain
    fallback_chain = _resolve_fallback_chain(session, primary_binding)

    # Create proxy context
    ctx = _ProxyContext(request, path, project_id, vault, session)

    attempted_bindings: list[str] = []
    last_error_response: Response | None = None
    last_plaintext: str | None = None

    for binding in fallback_chain:
        attempted_bindings.append(binding.service_name)
        try:
            resp, secret, plaintext = await _proxy_single_binding(ctx, binding)
            last_plaintext = plaintext

            # Check if request succeeded
            if resp.status_code < 400:
                # Success - reset failure state and return
                _reset_binding_failure_state(binding)
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                _LOG.info(
                    "proxy_success",
                    service=binding.service_name,
                    attempted=attempted_bindings,
                )
                return resp

            # Check if error should trigger fallback
            if _should_trigger_fallback(resp.status_code):
                cooldown_seconds = _FALLBACK_COOLDOWN_429 if resp.status_code == 429 else _FALLBACK_COOLDOWN_5XX
                _set_binding_cooldown(binding, cooldown_seconds)
                try:
                    session.commit()
                except Exception:
                    session.rollback()
                _LOG.warning(
                    "proxy_fallback_triggered",
                    service=binding.service_name,
                    status=resp.status_code,
                    next_fallback=len(attempted_bindings) < len(fallback_chain),
                )
                last_error_response = resp
                continue
            else:
                # Non-retriable error (400, 401, 403, etc.) - return immediately
                return resp

        except HTTPException:
            # HTTPException from secret/binding validation - don't fallback
            raise
        except Exception as exc:
            # Unexpected error - set cooldown and try next
            _set_binding_cooldown(binding, _FALLBACK_COOLDOWN_5XX)
            try:
                session.commit()
            except Exception:
                session.rollback()
            _LOG.error(
                "proxy_binding_error",
                service=binding.service_name,
                error=str(exc),
            )
            last_error_response = JSONResponse(
                status_code=502,
                content={
                    "ok": False,
                    "error": str(exc),
                    "service": binding.service_name,
                    "suggestion": "Unexpected error during proxy request.",
                },
            )
            continue

    # All fallbacks exhausted
    _LOG.error(
        "proxy_all_fallbacks_exhausted",
        primary=service_name,
        attempted=attempted_bindings,
    )
    if last_error_response:
        # Return last error with additional context
        try:
            body = json.loads(last_error_response.body)
            body["attempted_bindings"] = attempted_bindings
            body["fallback_exhausted"] = True
            return JSONResponse(
                status_code=last_error_response.status_code,
                content=body,
            )
        except Exception:
            return last_error_response

    return JSONResponse(
        status_code=503,
        content={
            "ok": False,
            "error": "All fallback bindings exhausted",
            "primary_binding": service_name,
            "attempted_bindings": attempted_bindings,
            "suggestion": "Check your API keys and quotas. All bindings in fallback chain failed.",
        },
    )


def _record_usage(
    session: Session,
    service_name: str,
    project_id: str | None,
    is_error: bool = False,
) -> None:
    """Increment daily usage counter for a proxy service."""
    from datetime import date

    today = date.today().isoformat()
    row = session.query(ProxyUsage).filter(
        ProxyUsage.service_name == service_name,
        ProxyUsage.project_id == project_id,
        ProxyUsage.date == today,
    ).first()
    if row is None:
        row = ProxyUsage(
            service_name=service_name,
            project_id=project_id,
            date=today,
            request_count=0,
            token_count=0,
            error_count=0,
        )
        session.add(row)
    row.request_count += 1
    if is_error:
        row.error_count += 1
    try:
        session.commit()
    except Exception:
        session.rollback()


def _update_service_status(
    session: Session,
    service_name: str,
    is_error: bool = False,
    error_message: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Update LLMServiceStatus after each call (R11).

    Records the result of the most recent call to each LLM service,
    enabling status dashboards without additional API calls.
    """
    if not _is_llm_service(service_name):
        return

    from datetime import datetime

    status_row = session.query(LLMServiceStatus).filter(
        LLMServiceStatus.service_name == service_name
    ).first()

    now = datetime.utcnow()
    status = "error" if is_error else "success"

    if status_row is None:
        status_row = LLMServiceStatus(
            service_name=service_name,
            last_call_at=now,
            last_call_status=status,
            last_call_error=error_message,
            last_call_latency_ms=latency_ms,
            last_success_at=now if not is_error else None,
            consecutive_failures=1 if is_error else 0,
        )
        session.add(status_row)
    else:
        status_row.last_call_at = now
        status_row.last_call_status = status
        status_row.last_call_error = error_message
        status_row.last_call_latency_ms = latency_ms
        if not is_error:
            status_row.last_success_at = now
            status_row.consecutive_failures = 0
        else:
            status_row.consecutive_failures += 1

    try:
        session.commit()
    except Exception:
        session.rollback()
