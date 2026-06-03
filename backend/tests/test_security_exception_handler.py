"""Security tests: unhandled exception handler must suppress raw details."""

from __future__ import annotations

from starlette.testclient import TestClient

from app.main import create_app


def test_500_never_leaks_exception_details():
    """An unhandled RuntimeError must return generic 500, not raw traceback."""
    from pathlib import Path
    from unittest.mock import patch

    with patch.object(Path, "is_dir", return_value=False):
        test_app = create_app()

    @test_app.get("/trigger-crash")
    def _crash():
        raise RuntimeError("internal secret: sk-DANGEROUS1234567890abcdef")

    with TestClient(test_app, raise_server_exceptions=False) as c:
        r = c.get("/trigger-crash")
        assert r.status_code == 500
        body = r.json()
        assert body["code"] == "INTERNAL_ERROR"
        assert body["detail"] == "Internal server error"
        assert "sk-DANGEROUS" not in r.text
        assert "secret" not in r.text.lower()
        assert "traceback" not in r.text.lower()


def test_secrets_api_value_never_in_list_response():
    """GET /api/secrets must never include a 'value' field (ciphertext or plaintext)."""
    test_app = create_app()
    with TestClient(test_app) as c:
        r = c.get("/api/secrets")
        if r.status_code == 200:
            data = r.json()
            for item in data.get("items", []):
                assert "value" not in item, "GET /api/secrets must not expose 'value'"


def test_health_endpoint_does_not_leak_config():
    """GET /health returns only status and vault state, no config or internal details."""
    test_app = create_app()
    with TestClient(test_app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        body = r.json()
        allowed_keys = {"status", "vault_unlocked"}
        assert set(body.keys()).issubset(allowed_keys), (
            f"health endpoint exposes unexpected keys: {set(body.keys()) - allowed_keys}"
        )
        assert body["status"] == "ok"
        for key in body:
            assert "password" not in key.lower()
            assert "secret" not in key.lower()
            assert "key" not in key.lower()
