"""Model catalog for GET /v1/models.

Lists models that are known to be available through the proxy.
This is a static list maintained alongside model_routing.py.

To add a new model:
1. Ensure the provider binding exists (check /proxy/ discovery endpoint)
2. Append an entry below following the ModelEntry structure.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.cursor_cli_routing import (
    CURSOR_MODEL_DESCRIPTIONS,
    CURSOR_SERVICE_NAME,
    all_cursor_caller_models,
)
from app.core.local_model_routing import EMBED_CODE, LOCAL_SERVICE_NAME, all_l_codes


@dataclass
class ModelEntry:
    id: str           # Exact model ID string (as sent to the upstream API)
    provider: str     # Human-readable provider name
    service: str      # Binding service_name in PolarPrivate
    description: str = ""


MODEL_CATALOG: list[ModelEntry] = [
    # ── 讯飞星火 MaaS 企业版 GLM-5.1 API ─────────────────────────────────────────
    # OpenAI 协议: https://maas-coding-api.cn-huabei-1.xf-yun.com/v2
    # Anthropic 协议: https://maas-coding-api.cn-huabei-1.xf-yun.com/anthropic
    ModelEntry(
        id="astron-code-latest",
        provider="xfyun",
        service="llm.glm51.enterprise",
        description="讯飞星火 MaaS 企业版 GLM-5.1 模型，支持 OpenAI/Anthropic 协议。",
    ),
    # ── MiniMax ───────────────────────────────────────────────────────────────
    ModelEntry(
        id="MiniMax-M3",
        provider="minimax",
        service="llm.minimax",
        description="MiniMax M3 旗舰；码 001 默认走此模型，Proxy 默认关闭 thinking 以提速。",
    ),
    # ── Aliyun / DashScope ───────────────────────────────────────────────────
    ModelEntry(
        id="qwen3.5-plus",
        provider="aliyun",
        service="llm.aliyun.codingplan",
        description="Qwen3.5 Plus，通用强力模型（原 qwen3.6-plus 已下线）。",
    ),
    ModelEntry(
        id="qwen3-max-2026-01-23",
        provider="aliyun",
        service="llm.aliyun.codingplan",
        description="Qwen3 Max，强大推理长文本模型。",
    ),
    # ── 智谱 GLM（讯飞星火企业版，非天翼云）────────────────────────────────────
    ModelEntry(
        id="GLM-5.1",
        provider="xfyun",
        service="llm.glm51.enterprise",
        description="智谱 GLM-5.1，讯飞星火 MaaS 企业版。",
    ),
    ModelEntry(
        id="GLM-5",
        provider="xfyun",
        service="llm.glm51.enterprise",
        description="智谱 GLM-5，讯飞星火 MaaS 企业版。",
    ),
    ModelEntry(
        id="GLM-5-Turbo",
        provider="xfyun",
        service="llm.glm51.enterprise",
        description="智谱 GLM-5 Turbo，讯飞星火 MaaS 企业版。",
    ),
    # ── Cloud capability codes (opaque; no vendor model names) ───────────────
    ModelEntry(id="000", provider="capability", service="llm.aliyun.codingplan", description="Cloud default balance."),
    ModelEntry(id="001", provider="capability", service="llm.minimax", description="Cloud fast tier → MiniMax-M3 (Token Plan)."),
    ModelEntry(id="010", provider="capability", service="llm.aliyun.codingplan", description="Cloud long-context tier."),
    ModelEntry(
        id="100",
        provider="capability",
        service="llm.minimax",
        description="Retired CTYun tier — requests route to 001 / MiniMax-M3.",
    ),
    ModelEntry(id="101", provider="capability", service="llm.aliyun.codingplan", description="Cloud vision-capable tier."),
    # ── Cursor Agent CLI (uses local `agent` login) ─────────────────────────
    *[
        ModelEntry(
            id=model_id,
            provider="cursor",
            service=CURSOR_SERVICE_NAME,
            description=CURSOR_MODEL_DESCRIPTIONS[model_id],
        )
        for model_id in all_cursor_caller_models()
    ],
    # ── Local chat slots (L-prefix; always listed) ─────────────────────────
    *[
        ModelEntry(
            id=code,
            provider="local",
            service=LOCAL_SERVICE_NAME,
            description={
                "L000": "Local chat — Qwen 8B (qwen3:8b).",
                "L100": "Local chat — Qwen 32B (qwen3:32b).",
                "L101": "Local vision — Qwen VLM 8B (qwen3-vl:8b).",
            }[code],
        )
        for code in all_l_codes()
    ],
    ModelEntry(
        id=EMBED_CODE,
        provider="local",
        service=LOCAL_SERVICE_NAME,
        description="Local embedding model slot (POST /v1/embeddings only).",
    ),
]
