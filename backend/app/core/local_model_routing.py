"""Opaque model codes → real Ollama model names (server-side only).

Local chat exposes **three** L-codes only (plus ``E000`` for embeddings):

  L000 → qwen3:8b        (8B 对话)
  L100 → qwen3:32b       (32B 对话，Q=1)
  L101 → qwen3-vl:8b     (8B VLM，Q=1,S=1 视觉槽)

Cloud chat still uses ``000``–``111``. See ``CAPABILITY_CODES.md``.
"""

from __future__ import annotations

import os
import re

LOCAL_SERVICE_NAME = "llm.local.ollama"

# Only these L-codes are valid (zero-compat; no L001/L010/…).
LOCAL_CHAT_CODES = frozenset({"L000", "L100", "L101"})

_L_CODE_RE = re.compile(r"^L[01]{3}$", re.IGNORECASE)

DEFAULT_OLLAMA_BY_L_CODE: dict[str, str] = {
    "L000": "qwen3:8b",
    "L100": "qwen3:32b",
    "L101": "qwen3-vl:8b",
}

EMBED_CODE = "E000"
DEFAULT_EMBED_MODEL = "qwen3-embedding:8b"


def ollama_base_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def normalize_l_code(model: str) -> str | None:
    m = (model or "").strip().upper()
    if m in LOCAL_CHAT_CODES:
        return m
    return None


def is_local_chat_code(model: str) -> bool:
    return normalize_l_code(model) is not None


def resolve_ollama_chat_model(l_code: str) -> str:
    """L-code → Ollama model tag (chat / VLM)."""
    code = normalize_l_code(l_code)
    if not code:
        raise ValueError(
            f"invalid L-code: {l_code!r} (use L000 8B, L100 32B, L101 VLM)"
        )
    env_key = f"OLLAMA_MODEL_{code}"
    return (
        os.environ.get(env_key)
        or os.environ.get("OLLAMA_MODEL")
        or DEFAULT_OLLAMA_BY_L_CODE[code]
    )


def all_l_codes() -> list[str]:
    return sorted(LOCAL_CHAT_CODES)


def normalize_embed_code(model: str) -> str | None:
    m = (model or "").strip().upper()
    if m == EMBED_CODE:
        return EMBED_CODE
    return None


def is_embed_code(model: str) -> bool:
    return normalize_embed_code(model) is not None


def resolve_ollama_embed_model(code: str = EMBED_CODE) -> str:
    canonical = normalize_embed_code(code)
    if not canonical:
        raise ValueError(f"invalid embedding code: {code!r} (use {EMBED_CODE})")
    return (
        os.environ.get("OLLAMA_EMBED_MODEL")
        or os.environ.get(f"OLLAMA_EMBED_MODEL_{canonical}")
        or DEFAULT_EMBED_MODEL
    )
