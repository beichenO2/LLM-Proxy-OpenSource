"""Hardcoded input caps and proxy chat body normalization."""

from __future__ import annotations

import json

from app.api import proxy as proxy_mod
from app.services import models_dev_limits as catalog


def test_input_threshold_half_context():
    assert catalog.input_token_threshold_for_model("MiniMax-M3") == 500000
    assert catalog.input_token_threshold_for_model("GLM-5.1") == 101376
    assert catalog.input_token_threshold_for_model("GLM-5") == 101376
    assert catalog.input_token_threshold_for_model("GLM-5-Turbo") == 100000


def test_glm_alias_model_id_lookup():
    assert catalog.max_context_tokens_for_model("z-ai/glm-5") == 202752
    assert catalog.max_context_tokens_for_model("zai-org/glm-5-turbo") == 200000


def test_unknown_model_has_no_cap():
    assert catalog.input_token_threshold_for_model("totally-unknown-xyz") is None


def test_prepare_body_strips_max_tokens_by_default():
    body = json.dumps({
        "model": "totally-unknown-xyz",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 333,
        "max_completion_tokens": 444,
    }).encode()
    out, truncated = proxy_mod._prepare_chat_proxy_body(body)
    obj = json.loads(out)
    assert "max_tokens" not in obj
    assert "max_completion_tokens" not in obj
    assert truncated is False


def test_prepare_body_keeps_max_tokens_when_env_set(monkeypatch):
    monkeypatch.setenv("PRIVPORTAL_FORWARD_MAX_TOKENS", "1")
    body = json.dumps({
        "model": "totally-unknown-xyz",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 99,
    }).encode()
    out, _ = proxy_mod._prepare_chat_proxy_body(body)
    obj = json.loads(out)
    assert obj.get("max_tokens") == 99


def test_truncation_when_over_catalog_half():
    """Truncation is disabled. Even long prompts must pass through unmodified."""
    long_piece = ("x\n" * 18000)
    msgs = [{"role": "system", "content": "sy"}]
    msgs += [{"role": "user", "content": f"h{i}-{long_piece}"} for i in range(14)]

    body = json.dumps({"model": "MiniMax-M3", "messages": msgs}).encode()
    out, truncated = proxy_mod._prepare_chat_proxy_body(body)
    assert truncated is False
    obj = json.loads(out)
    assert len(obj["messages"]) == len(msgs)


def test_unknown_model_does_not_truncate():
    long_piece = ("x\n" * 8000)
    msgs = [{"role": "system", "content": "sy"}]
    msgs += [{"role": "user", "content": f"h{i}-{long_piece}"} for i in range(14)]
    body = json.dumps({"model": "unknown-model-id", "messages": msgs}).encode()
    out, truncated = proxy_mod._prepare_chat_proxy_body(body)
    assert truncated is False
    obj = json.loads(out)
    assert len(obj["messages"]) == len(msgs)
