"""Hardcoded context windows for models routed by PolarPrivate LLM proxy.

The routed model set is small and stable, so we keep a static table instead of
fetching models.dev at runtime.
"""

from __future__ import annotations

_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # 讯飞星火 MaaS 企业版 GLM-5.1
    "astron-code-latest": 128000,
    # MiniMax
    "minimax-m3": 1_000_000,
    # Aliyun codingPlan
    "qwen3-coder-plus": 1048576,
    "qwen3.6-plus": 1000000,
    "qwen3-max-2026-01-23": 262144,
    "qwen-vl-max": 131072,
    "kimi-k2.5": 262144,
    # CTYun routing (GLM-5 family)
    # models.dev shows these mostly in the ~200k context range.
    "glm-5": 202752,
    "glm-5.1": 202752,
    "glm-5-turbo": 200000,
}

_MODEL_ALIASES: dict[str, str] = {
    # Common provider-prefixed IDs seen in models.dev / gateways
    "z-ai/glm-5": "glm-5",
    "zai-org/glm-5": "glm-5",
    "z-ai/glm-5.1": "glm-5.1",
    "zai-org/glm-5.1": "glm-5.1",
    "z-ai/glm-5-turbo": "glm-5-turbo",
    "zai-org/glm-5-turbo": "glm-5-turbo",
}


def max_context_tokens_for_model(model_id: str | None) -> int | None:
    """Return hardcoded context window for a routed model id."""
    if not model_id or not isinstance(model_id, str):
        return None
    key = model_id.lower().strip()
    key = _MODEL_ALIASES.get(key, key)
    return _MODEL_CONTEXT_WINDOWS.get(key)


def input_token_threshold_for_model(model_id: str | None) -> int | None:
    """Proxy input estimate cap: context / 2; unknown model means no cap."""
    ctx = max_context_tokens_for_model(model_id)
    if ctx is not None and ctx > 0:
        return max(ctx // 2, 1)
    return None
