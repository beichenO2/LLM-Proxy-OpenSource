"""Gateway tests for Cursor CLI proxy route."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.services.vault import VaultService


@pytest.fixture()
def gateway_client(tmp_path, monkeypatch):
    db_path = tmp_path / "cursor-gateway.db"
    monkeypatch.setenv("PRIVPORTAL_DATABASE_URL", f"sqlite:///{db_path}")

    from app.db import session as session_mod

    engine = session_mod.create_sync_engine(f"sqlite:///{db_path}")
    session_mod._engine = engine
    session_mod.SessionLocal.configure(bind=engine)

    from app.services.db_bootstrap import run_migrations_to_head

    run_migrations_to_head(f"sqlite:///{db_path}")

    from sqlalchemy.orm import Session

    with Session(engine) as s:
        VaultService.create_new_database(s, "cursorpass")
        s.commit()

    app.state.vault = VaultService()
    client = TestClient(app)
    yield client
    engine.dispose()


class TestCursorGateway:
    def test_models_lists_c000_when_cli_available(self, gateway_client, monkeypatch):
        monkeypatch.setattr("app.api.v1_gateway.cursor_cli_available", lambda: True)
        r = gateway_client.post("/api/vault/unlock", json={"master_password": "cursorpass"})
        assert r.status_code == 200

        r = gateway_client.get("/v1/models")
        assert r.status_code == 200
        ids = [m["id"] for m in r.json()["data"]]
        assert "C000" in ids

    def test_chat_routes_to_cursor_adapter(self, gateway_client, monkeypatch):
        monkeypatch.setattr("app.api.v1_gateway.cursor_cli_available", lambda: True)

        async def fake_chat(*, caller_model: str, messages):
            assert caller_model == "C000"
            assert messages[-1]["content"] == "ping"
            return {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": caller_model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "pong"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        with patch(
            "app.api.v1_gateway.cursor_chat_completion",
            new=AsyncMock(side_effect=fake_chat),
        ):
            r = gateway_client.post(
                "/v1/chat/completions",
                json={
                    "model": "C000",
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )

        assert r.status_code == 200
        body = r.json()
        assert body["model"] == "C000"
        assert body["choices"][0]["message"]["content"] == "pong"

    def test_stream_not_supported(self, gateway_client, monkeypatch):
        monkeypatch.setattr("app.api.v1_gateway.cursor_cli_available", lambda: True)
        r = gateway_client.post(
            "/v1/chat/completions",
            json={
                "model": "C000",
                "stream": True,
                "messages": [{"role": "user", "content": "ping"}],
            },
        )
        assert r.status_code == 422
        body = r.json()
        detail = body["detail"]
        if isinstance(detail, dict):
            assert detail["code"] == "STREAM_NOT_SUPPORTED"
        else:
            assert "streaming" in detail.lower()
