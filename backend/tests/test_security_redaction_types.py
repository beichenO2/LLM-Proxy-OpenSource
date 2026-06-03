"""Security tests: redaction covers bytes, tuples, and nested structures."""

from __future__ import annotations

from app.logging_config import (
    _redact_value,
    clear_registered_secrets,
    register_secrets_for_redaction,
)


def test_redact_bytes_value():
    clear_registered_secrets()
    register_secrets_for_redaction(["TOPSECRET"])
    result = _redact_value(b"key=TOPSECRET&foo=bar")
    assert isinstance(result, bytes)
    assert b"TOPSECRET" not in result
    assert b"[REDACTED]" in result
    clear_registered_secrets()


def test_redact_tuple_value():
    clear_registered_secrets()
    register_secrets_for_redaction(["mysecret"])
    result = _redact_value(("safe", "contains mysecret here", 42))
    assert isinstance(result, tuple)
    assert "mysecret" not in result[1]
    assert "[REDACTED]" in result[1]
    assert result[2] == 42
    clear_registered_secrets()


def test_redact_nested_dict_list():
    clear_registered_secrets()
    register_secrets_for_redaction(["hidden"])
    data = {
        "outer": [{"inner": "the hidden value"}],
        "plain": "safe",
    }
    result = _redact_value(data)
    assert "hidden" not in result["outer"][0]["inner"]
    assert result["plain"] == "safe"
    clear_registered_secrets()


def test_redact_no_secrets_registered():
    clear_registered_secrets()
    result = _redact_value("nothing to redact sk-abc")
    assert result == "nothing to redact sk-abc"
