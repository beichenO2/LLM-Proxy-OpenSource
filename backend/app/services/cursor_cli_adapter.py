"""Invoke Cursor Agent CLI and return OpenAI-compatible chat responses."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from app.core.cursor_cli_routing import (
    agent_bin,
    agent_subprocess_env,
    agent_timeout_seconds,
    cursor_workspace,
    resolve_cursor_cli_slug,
)
from app.logging_config import get_logger

_LOG = get_logger(__name__)
_CLI_LOCK = asyncio.Lock()

# Transient Cursor CLI / network errors worth one retry.
_RETRY_MARKERS = (
    "connection lost",
    "reconnecting",
    "socket disconnected",
    "nghttp2",
    "etimedout",
    "econnreset",
)


class CursorCliError(Exception):
    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class CursorCliTimeout(CursorCliError):
    pass


def messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = [
        "Do not inspect files, run tools, or use MCP. Reply with text only.",
    ]
    for msg in messages:
        role = str(msg.get("role", "user")).upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            text_bits: list[str] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_bits.append(str(part.get("text", "")))
            content = "\n".join(text_bits)
        parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


def build_chat_completion(content: str, caller_model: str, prompt: str) -> dict[str, Any]:
    prompt_tokens = max(1, len(prompt.split()))
    completion_tokens = max(1, len(content.split()))
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": caller_model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _parse_agent_stdout(raw: str, stderr_text: str) -> str:
    if not raw:
        raise CursorCliError(stderr_text or "Cursor CLI returned empty output")

    if raw.startswith("{"):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CursorCliError(f"Cursor CLI returned invalid JSON: {raw[:500]}") from exc
        if payload.get("is_error"):
            raise CursorCliError(
                str(payload.get("result") or payload.get("message") or "Cursor CLI error")
            )
        result = payload.get("result")
        if isinstance(result, str) and result.strip():
            return result.strip()
        raise CursorCliError("Cursor CLI returned an empty assistant message")

    return raw.strip()


def _should_retry(detail: str) -> bool:
    lowered = detail.lower()
    return any(marker in lowered for marker in _RETRY_MARKERS)


async def _run_agent_once(prompt: str, model_slug: str, workspace: str) -> str:
    cmd = [
        agent_bin(),
        "-p",
        "--trust",
        "--approve-mcps",
        "--sandbox",
        "disabled",
        "--output-format",
        "text",
        "--model",
        model_slug,
        "--workspace",
        workspace,
        prompt,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace,
            env=agent_subprocess_env(),
        )
    except FileNotFoundError as exc:
        raise CursorCliError(
            f"Cursor Agent CLI not found at {agent_bin()!r}. "
            "Install Cursor CLI and set CURSOR_AGENT_BIN if needed.",
        ) from exc

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=agent_timeout_seconds(),
        )
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise CursorCliTimeout(
            f"Cursor CLI timed out after {agent_timeout_seconds():.0f}s",
        ) from exc

    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        detail = stderr_text or f"Cursor CLI exited with code {proc.returncode}"
        raise CursorCliError(detail, exit_code=proc.returncode)

    raw = stdout.decode("utf-8", errors="replace").strip()
    return _parse_agent_stdout(raw, stderr_text)


async def invoke_cursor_agent(prompt: str, caller_model: str) -> str:
    model_slug = resolve_cursor_cli_slug(caller_model)
    workspace = cursor_workspace()
    _LOG.info(
        "cursor_cli_invoke",
        caller_model=caller_model,
        model_slug=model_slug,
        workspace=workspace,
    )

    last_error: CursorCliError | None = None
    async with _CLI_LOCK:
        for attempt in (1, 2, 3):
            try:
                return await _run_agent_once(prompt, model_slug, workspace)
            except CursorCliError as exc:
                last_error = exc
                if attempt < 3 and _should_retry(str(exc)):
                    _LOG.warning("cursor_cli_retry", attempt=attempt, error=str(exc)[:200])
                    await asyncio.sleep(3 * attempt)
                    continue
                raise
    if last_error:
        raise last_error
    raise CursorCliError("Cursor CLI failed without details")


async def chat_completion(
    *,
    caller_model: str,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt = messages_to_prompt(messages)
    content = await invoke_cursor_agent(prompt, caller_model)
    return build_chat_completion(content, caller_model, prompt)
