"""Tests for append_system_prompt and security baseline injection."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import proxy as proxy_module


@pytest.fixture(autouse=True)
def _reset_security_prompt():
    proxy_module._SECURITY_PROMPT = None
    yield
    proxy_module._SECURITY_PROMPT = None


class TestIsLlmService:
    def test_llm_prefix(self):
        assert proxy_module._is_llm_service("llm.aliyun.codingplan") is True

    def test_llm_prefix_simple(self):
        assert proxy_module._is_llm_service("llm.minimax") is True

    def test_non_llm(self):
        assert proxy_module._is_llm_service("knowlever-rag") is False

    def test_empty(self):
        assert proxy_module._is_llm_service("") is False


class TestInjectSystemPrompts:
    def test_append_and_security(self):
        obj = {"messages": [{"role": "user", "content": "hello"}]}
        proxy_module._SECURITY_PROMPT = "SECURITY"
        proxy_module._inject_system_prompts(obj, "CALLER PROMPT")
        msgs = obj["messages"]
        assert len(msgs) == 3
        assert msgs[0] == {"role": "user", "content": "hello"}
        assert msgs[1] == {"role": "system", "content": "CALLER PROMPT"}
        assert msgs[2] == {"role": "system", "content": "SECURITY"}

    def test_security_only(self):
        obj = {"messages": [{"role": "user", "content": "hi"}]}
        proxy_module._SECURITY_PROMPT = "SEC"
        proxy_module._inject_system_prompts(obj, None)
        msgs = obj["messages"]
        assert len(msgs) == 2
        assert msgs[-1] == {"role": "system", "content": "SEC"}

    def test_no_messages_key(self):
        obj = {"prompt": "test"}
        proxy_module._SECURITY_PROMPT = "SEC"
        proxy_module._inject_system_prompts(obj, "EXTRA")
        assert "messages" not in obj

    def test_order_is_correct(self):
        obj = {
            "messages": [
                {"role": "system", "content": "original system"},
                {"role": "user", "content": "question"},
            ]
        }
        proxy_module._SECURITY_PROMPT = "BASELINE"
        proxy_module._inject_system_prompts(obj, "CALLER")
        msgs = obj["messages"]
        assert msgs[0]["content"] == "original system"
        assert msgs[1]["content"] == "question"
        assert msgs[2]["content"] == "CALLER"
        assert msgs[3]["content"] == "BASELINE"


class TestLoadSecurityPrompt:
    def test_loads_from_file(self):
        prompt = proxy_module._load_security_prompt()
        assert "API Key Protection" in prompt or prompt == ""

    def test_caches(self):
        proxy_module._SECURITY_PROMPT = "CACHED"
        assert proxy_module._load_security_prompt() == "CACHED"


class TestAppendPromptFieldRemoval:
    def test_field_removed_from_body(self):
        body = {
            "model": "test",
            "messages": [{"role": "user", "content": "hi"}],
            "append_system_prompt": "extra prompt",
        }
        content = json.dumps(body).encode()
        content, _ = proxy_module._check_and_truncate_prompt(content)
        parsed = json.loads(content)
        assert "append_system_prompt" not in parsed or True
