"""Tests for Cursor CLI routing and adapter helpers."""

from __future__ import annotations

import json

from app.core.cursor_cli_routing import (
    CURSOR_SERVICE_NAME,
    resolve_cursor_caller,
    resolve_cursor_cli_slug,
)
from app.core.model_routing import (
    caller_facing_model,
    is_opaque_caller_model,
    resolve_model_and_service,
)
from app.services.cursor_cli_adapter import (
    _parse_agent_stdout,
    _should_retry,
    build_chat_completion,
    messages_to_prompt,
)


class TestCursorRouting:
    def test_c000_resolves(self) -> None:
        model, service = resolve_model_and_service("C000")
        assert model == "C000"
        assert service == CURSOR_SERVICE_NAME

    def test_readable_slug_resolves(self) -> None:
        model, service = resolve_model_and_service("composer-2.5-fast")
        assert model == "composer-2.5-fast"
        assert service == CURSOR_SERVICE_NAME

    def test_unknown_cursor_code(self) -> None:
        assert resolve_model_and_service("C001") == (None, None)

    def test_both_names_share_cli_slug(self) -> None:
        assert resolve_cursor_cli_slug("C000") == "composer-2.5-fast"
        assert resolve_cursor_cli_slug("composer-2.5-fast") == "composer-2.5-fast"

    def test_response_echoes_requested_name(self) -> None:
        assert is_opaque_caller_model("C000") is True
        assert is_opaque_caller_model("composer-2.5-fast") is True
        assert caller_facing_model("C000", "composer-2.5-fast") == "C000"
        assert caller_facing_model("composer-2.5-fast", "composer-2.5-fast") == "composer-2.5-fast"

    def test_resolve_cursor_caller(self) -> None:
        assert resolve_cursor_caller("c000") == "C000"
        assert resolve_cursor_caller("Composer-2.5-Fast") == "composer-2.5-fast"

    def test_agent_bin_uses_home_fallback(self, monkeypatch) -> None:
        monkeypatch.delenv("CURSOR_AGENT_BIN", raising=False)
        monkeypatch.setattr("app.core.cursor_cli_routing.shutil.which", lambda _: None)
        from app.core.cursor_cli_routing import agent_bin, cursor_cli_available

        path = agent_bin()
        assert path.endswith("/.local/bin/agent")
        assert cursor_cli_available() is True


class TestCursorAdapterHelpers:
    def test_messages_to_prompt(self) -> None:
        prompt = messages_to_prompt([
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ])
        assert "SYSTEM: You are helpful." in prompt
        assert "USER: Hello" in prompt

    def test_build_chat_completion(self) -> None:
        payload = build_chat_completion("OK", "C000", "USER: ping")
        assert payload["model"] == "C000"
        assert payload["choices"][0]["message"]["content"] == "OK"
        assert payload["usage"]["total_tokens"] >= 2

    def test_parse_text_stdout(self) -> None:
        assert _parse_agent_stdout("OK", "") == "OK"

    def test_parse_json_stdout(self) -> None:
        raw = json.dumps({"type": "result", "result": "OK", "is_error": False})
        assert _parse_agent_stdout(raw, "") == "OK"

    def test_should_retry_connection_errors(self) -> None:
        assert _should_retry("Connection lost, reconnecting") is True
        assert _should_retry("validation error") is False


class TestCursorSubprocessEnv:
    def test_agent_subprocess_env_explicit_override(self, monkeypatch) -> None:
        from app.core.cursor_cli_routing import agent_subprocess_env

        monkeypatch.setenv("CURSOR_AGENT_HTTP_PROXY", "http://127.0.0.1:9999")
        env = agent_subprocess_env()
        assert env["HTTP_PROXY"] == "http://127.0.0.1:9999"
        assert env["HTTPS_PROXY"] == "http://127.0.0.1:9999"
