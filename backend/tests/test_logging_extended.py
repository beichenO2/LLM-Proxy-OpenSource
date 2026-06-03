"""Extended logging tests — redaction edge cases, bytes, tuples."""

from __future__ import annotations

from app.logging_config import (
    _redact_string,
    _redact_value,
    clear_registered_secrets,
    redact_processor,
    register_secrets_for_redaction,
    sanitize_user_facing_string,
)


def test_redact_string_empty_set():
    """With no registered secrets, string passes through unchanged."""
    clear_registered_secrets()
    assert _redact_string("hello world") == "hello world"


def test_redact_value_bytes():
    """Bytes containing registered secret are redacted."""
    clear_registered_secrets()
    register_secrets_for_redaction(["my-secret"])
    result = _redact_value(b"token is my-secret here")
    assert b"[REDACTED]" in result
    assert b"my-secret" not in result
    clear_registered_secrets()


def test_redact_value_bytes_no_match():
    """Bytes without registered secret pass through unchanged."""
    clear_registered_secrets()
    register_secrets_for_redaction(["my-secret"])
    original = b"no match here"
    result = _redact_value(original)
    assert result is original
    clear_registered_secrets()


def test_redact_value_tuple():
    """Tuples are recursively redacted and returned as tuples."""
    clear_registered_secrets()
    register_secrets_for_redaction(["topsecret"])
    result = _redact_value(("contains topsecret", "clean"))
    assert isinstance(result, tuple)
    assert "[REDACTED]" in result[0]
    assert result[1] == "clean"
    clear_registered_secrets()


def test_redact_value_nested_dict():
    """Nested dicts are recursively redacted."""
    clear_registered_secrets()
    register_secrets_for_redaction(["api-key-123"])
    result = _redact_value({"outer": {"inner": "value is api-key-123"}})
    assert "[REDACTED]" in result["outer"]["inner"]
    clear_registered_secrets()


def test_redact_value_list():
    clear_registered_secrets()
    register_secrets_for_redaction(["listval"])
    result = _redact_value(["has listval", "clean"])
    assert "[REDACTED]" in result[0]
    assert result[1] == "clean"
    clear_registered_secrets()


def test_redact_processor_no_secrets():
    """With empty redaction set, processor returns event_dict unchanged."""
    clear_registered_secrets()
    ed = {"event": "test", "key": "value"}
    result = redact_processor(None, "info", ed)
    assert result is ed


def test_sanitize_sk_pattern():
    """sk-like patterns are redacted even without registration."""
    clear_registered_secrets()
    result = sanitize_user_facing_string("key is sk-abcdefghijklmno very secret")
    assert "sk-" not in result
    assert "[REDACTED]" in result


def test_register_empty_string_ignored():
    """Empty strings are not added to redaction set."""
    clear_registered_secrets()
    register_secrets_for_redaction(["", "valid-secret"])
    result = _redact_string("has valid-secret here")
    assert "[REDACTED]" in result
    assert "valid-secret" not in result
    clear_registered_secrets()


def test_configure_logging_json_format():
    """JSON format renderer can be selected without error."""
    from app.logging_config import configure_logging
    configure_logging(json_format=True)
    configure_logging(json_format=False)
