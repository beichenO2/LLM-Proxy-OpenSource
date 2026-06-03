"""MiniMax upstream defaults for PolarPrivate /v1 gateway."""

from __future__ import annotations

import os
from typing import Any

# Official OpenAI-compatible id (https://platform.minimax.io/docs/api-reference/api-overview)
MINIMAX_M3_MODEL_ID = "MiniMax-M3"


def _m3_thinking_default() -> str:
    """disabled = lower latency; adaptive = deeper reasoning (MiniMax docs)."""
    return os.environ.get("POLARPRIVATE_MINIMAX_M3_THINKING", "disabled").strip().lower()


def apply_minimax_upstream_defaults(obj: dict[str, Any]) -> None:
    """Inject MiniMax-M3 request knobs before forwarding to llm.minimax binding."""
    model = str(obj.get("model", "")).strip()
    if model != MINIMAX_M3_MODEL_ID:
        return

    extra = obj.get("extra_body")
    if not isinstance(extra, dict):
        extra = {}

    if extra.get("thinking") is None:
        mode = _m3_thinking_default()
        thinking_type = mode if mode in {"disabled", "adaptive"} else "disabled"
        extra["thinking"] = {"type": thinking_type}

    obj["extra_body"] = extra
