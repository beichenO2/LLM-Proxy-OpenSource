"""Comprehensive security regression tests covering multiple attack surfaces."""

from __future__ import annotations

import re
from pathlib import Path


def test_secret_out_model_excludes_value_field():
    """SecretOut Pydantic model must NOT have a 'value' field."""
    from app.api.secrets import SecretOut

    fields = set(SecretOut.model_fields.keys())
    assert "value" not in fields, "SecretOut must never expose 'value'"


def test_binding_out_model_excludes_secret_value():
    """BindingOut must not expose secret value or ciphertext."""
    from app.api.bindings import BindingOut

    fields = set(BindingOut.model_fields.keys())
    assert "value" not in fields
    assert "ciphertext" not in fields


def test_no_print_statements_in_app_source():
    """No print() calls in production code (could leak secrets to stdout)."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    print_re = re.compile(r"^\s*print\s*\(", re.MULTILINE)
    violations = []
    for py in app_dir.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        text = py.read_text(encoding="utf-8")
        if print_re.search(text):
            violations.append(str(py.relative_to(app_dir)))
    assert not violations, f"print() found in production code: {violations}"


def test_no_debug_logging_of_request_body_in_proxy():
    """Proxy module must not log request/response bodies (D-70)."""
    proxy_src = Path(__file__).resolve().parents[1] / "app" / "api" / "proxy.py"
    text = proxy_src.read_text(encoding="utf-8")
    dangerous_patterns = [
        r"_LOG\.\w+\(.*content",
        r"_LOG\.\w+\(.*body",
        r"_LOG\.\w+\(.*payload",
        r"_LOG\.\w+\(.*plaintext",
    ]
    for pattern in dangerous_patterns:
        assert not re.search(pattern, text), (
            f"proxy.py must not log bodies/plaintext: matched {pattern}"
        )


def test_cors_origins_are_localhost_only():
    """CORS allow_origins must be restricted to localhost."""
    from app.main import create_app

    test_app = create_app()
    cors_mw = None
    for mw in test_app.user_middleware:
        if "CORS" in str(mw.cls):
            cors_mw = mw
            break
    assert cors_mw is not None, "CORS middleware not found"
    origins = cors_mw.kwargs.get("allow_origins", [])
    for origin in origins:
        assert "127.0.0.1" in origin or "localhost" in origin, (
            f"CORS origin must be localhost: {origin}"
        )


def test_api_host_defaults_to_localhost():
    """Settings.api_host must default to 127.0.0.1."""
    from app.core.config import Settings

    assert Settings().api_host == "127.0.0.1"


def test_no_0000_bind_in_source():
    """Source code must not contain 0.0.0.0 bind addresses."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    for py in app_dir.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        text = py.read_text(encoding="utf-8")
        assert "0.0.0.0" not in text, f"0.0.0.0 found in {py}"


def test_reveal_endpoint_is_post_not_get():
    """Secret reveal must use POST (not GET) to avoid URL-logged plaintext."""
    from app.main import create_app

    test_app = create_app()
    reveal_routes = [
        r for r in test_app.routes
        if hasattr(r, "path") and "reveal" in getattr(r, "path", "")
    ]
    for route in reveal_routes:
        methods = getattr(route, "methods", set())
        assert "GET" not in methods, f"Reveal must not allow GET: {route.path}"
