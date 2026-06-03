"""Model → binding routing table for the /v1 unified LLM gateway.

To add a new provider:
1. Add the binding via PolarPrivate UI or API (POST /api/bindings)
2. Append a new entry here: (model_prefix, service_name)

Order matters: more specific prefixes should come first.
"""

from __future__ import annotations

import os

from app.core.cursor_cli_routing import CURSOR_SERVICE_NAME, is_cursor_caller_model, resolve_cursor_caller
from app.core.local_model_routing import LOCAL_SERVICE_NAME, is_local_chat_code, normalize_l_code


def fast_minimax_model() -> str:
    """MiniMax slot for capability code 001 (default: current standard MiniMax-M3)."""
    return os.environ.get("POLARPRIVATE_MINIMAX_FAST_MODEL", "MiniMax-M3").strip()


# Cloud capability codes (3-bit QCS) — opaque to callers; mapped server-side only.
# 天翼云 llm.ctyun.codingplan 已移除；原 100/110/111 在 resolve 中重定向到 001/MiniMax。
CAPABILITY_CLOUD_MAP: dict[str, tuple[str, str]] = {
    "000": ("qwen3.5-plus", "llm.aliyun.codingplan"),
    "001": ("MiniMax-M3", "llm.minimax"),  # overridden in resolve_model_and_service
    "010": ("qwen3-max-2026-01-23", "llm.aliyun.codingplan"),
    "101": ("qwen3.5-plus", "llm.aliyun.codingplan"),
}

# Retired CTYun capability codes → same as 001 (MiniMax-M3).
CTYUN_RETIRED_CAPABILITY_CODES = frozenset({"100", "110", "111"})

STRICT_MODEL_MAP = {
    # ── 智谱 GLM 企业版 API（讯飞星火 MaaS）──
    "astron-code": "astron-code-latest",
    "astron-code-latest": "astron-code-latest",
    # GLM 别名 → 讯飞星火企业版（不再走天翼云）
    "glm": "GLM-5.1",
    "glm-5.1": "GLM-5.1",
    "glm-5": "GLM-5",
    "glm-5-turbo": "GLM-5-Turbo",
    "glm-turbo": "GLM-5-Turbo",
    # ── 阿里云 codingPlan ──
    # ⚠️ Ali 白名单：仅允许 qwen3.5-plus 和 qwen3-max（最好的两个模型）
    # qwen3.6-plus 已被平台下线，实际可用的是 qwen3.5-plus
    "qwen-plus": "qwen3.5-plus",
    "qwen3.5-plus": "qwen3.5-plus",
    "qwen3.6-plus": "qwen3.5-plus",
    "qwen-max": "qwen3-max-2026-01-23",
    "qwen3-max-2026-01-23": "qwen3-max-2026-01-23",
    # ── MiniMax ──
    "minimax": "MiniMax-M3",
    "minimax-m3": "MiniMax-M3",
}

MODEL_SERVICE_MAP = {
    # 讯飞星火 MaaS 企业版 GLM-5.1 API
    # OpenAI 协议: https://maas-coding-api.cn-huabei-1.xf-yun.com/v2
    # Anthropic 协议: https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic
    "astron-code-latest": "llm.glm51.enterprise",
    "GLM-5.1": "llm.glm51.enterprise",
    "GLM-5": "llm.glm51.enterprise",
    "GLM-5-Turbo": "llm.glm51.enterprise",
    # 阿里云 codingPlan（仅白名单模型）
    "qwen3.5-plus": "llm.aliyun.codingplan",
    "qwen3-max-2026-01-23": "llm.aliyun.codingplan",
    # MiniMax (OpenAI-compatible https://api.minimax.io/v1)
    "MiniMax-M3": "llm.minimax",
}

# ── 负载均衡组 ──────────────────────────────────────────────────────────────
# 模型名 → [{service, weight}, ...]；按权重随机选择提供源。
# 不在组内的模型仍走 MODEL_SERVICE_MAP 单源映射。
# 与 fallback 机制独立：负载均衡是主动分配，fallback 是被动切换。

LOAD_BALANCE_GROUPS: dict[str, list[dict]] = {
    # 天翼云已下线；GLM-5.1 仅讯飞星火企业版单源
    "GLM-5.1": [
        {"service": "llm.glm51.enterprise", "weight": 1},
    ],
}


def get_load_balance_group(model: str) -> list[dict] | None:
    """Return the load-balance group for *model*, or None if single-source."""
    return LOAD_BALANCE_GROUPS.get(model)


def select_service_by_weight(services: list[dict]) -> str:
    """Weighted random selection among service candidates."""
    import random
    total = sum(s["weight"] for s in services)
    r = random.random() * total
    cumulative = 0
    for s in services:
        cumulative += s["weight"]
        if r <= cumulative:
            return s["service"]
    return services[-1]["service"]


def resolve_model_and_service(model: str) -> tuple[str, str] | tuple[None, None]:
    """Return (resolved_id, service_name).

    * Cloud capability codes ``000``–``111`` → upstream vendor models (hidden from callers).
    * Local codes ``L000`` / ``L100`` / ``L101`` only → ``llm.local.ollama``.
    * Zero-compat: only opaque codes above; no legacy model name aliases.
    """
    raw = (model or "").strip()
    if not raw:
        return None, None

    l_code = normalize_l_code(raw)
    if l_code:
        return l_code, LOCAL_SERVICE_NAME

    c_caller = resolve_cursor_caller(raw)
    if c_caller:
        return c_caller, CURSOR_SERVICE_NAME

    if len(raw) == 3 and all(c in "01" for c in raw):
        if raw == "001" or raw in CTYUN_RETIRED_CAPABILITY_CODES:
            return fast_minimax_model(), "llm.minimax"
        cap = CAPABILITY_CLOUD_MAP.get(raw)
        if cap:
            return cap

    # Explicit upstream model ids (e.g. MiniMax-M3)
    if raw in MODEL_SERVICE_MAP:
        return raw, MODEL_SERVICE_MAP[raw]
    alias = STRICT_MODEL_MAP.get(raw.lower())
    if alias and alias in MODEL_SERVICE_MAP:
        return alias, MODEL_SERVICE_MAP[alias]

    return None, None


def is_opaque_caller_model(model: str) -> bool:
    """True when API should echo *model* as-is (capability / L-code), not upstream name."""
    raw = (model or "").strip()
    return (
        is_local_chat_code(raw)
        or is_cursor_caller_model(raw)
        or (len(raw) == 3 and all(c in "01" for c in raw))
    )


def caller_facing_model(requested: str, resolved_upstream: str) -> str:
    """Model id returned to clients (avoid leaking vendor / Ollama tags)."""
    if is_opaque_caller_model(requested):
        l = normalize_l_code(requested)
        if l:
            return l
        c = resolve_cursor_caller(requested)
        if c:
            return c
        if len(requested.strip()) == 3:
            return requested.strip()
    return requested.strip() or resolved_upstream


def get_all_registered_services() -> list[str]:
    """Return all unique service names from MODEL_SERVICE_MAP.

    Used by test_center.py to query LLM service status for all registered services.
    """
    services = list(set(MODEL_SERVICE_MAP.values()))
    if LOCAL_SERVICE_NAME not in services:
        services.append(LOCAL_SERVICE_NAME)
    if CURSOR_SERVICE_NAME not in services:
        services.append(CURSOR_SERVICE_NAME)
    return services
