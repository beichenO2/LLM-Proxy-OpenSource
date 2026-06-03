"""Tests for LogBuffer — ring buffer behavior, edge cases, message truncation."""

from __future__ import annotations

from app.services.log_buffer import clear_log_buffer_for_testing, get_log_buffer


def test_get_log_buffer_returns_singleton():
    buf1 = get_log_buffer()
    buf2 = get_log_buffer()
    assert buf1._entries is buf2._entries


def test_clear_log_buffer():
    buf = get_log_buffer()
    buf.append({"event": "test-clear", "level": "info"}, "info")
    clear_log_buffer_for_testing()
    assert len(buf.snapshot_newest_first()) == 0


def test_append_basic_event():
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    buf.append(
        {"event": "hello", "level": "info", "timestamp": "2026-01-01T00:00:00", "logger": "test"},
        "info",
    )
    entries = buf.snapshot_newest_first()
    assert len(entries) == 1
    assert entries[0]["message"] == "hello"
    assert entries[0]["level"] == "INFO"
    assert entries[0]["source"] == "test"
    assert entries[0]["timestamp"] == "2026-01-01T00:00:00"


def test_append_with_integer_level():
    """Integer level values are converted via logging.getLevelName."""
    clear_log_buffer_for_testing()
    import logging

    buf = get_log_buffer()
    buf.append({"event": "int-level", "level": logging.WARNING}, "warning")
    entries = buf.snapshot_newest_first()
    assert entries[0]["level"] == "WARNING"


def test_append_no_level_uses_method_name():
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    buf.append({"event": "no-level"}, "debug")
    entries = buf.snapshot_newest_first()
    assert entries[0]["level"] == "DEBUG"


def test_append_no_timestamp():
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    buf.append({"event": "no-ts", "level": "info"}, "info")
    entries = buf.snapshot_newest_first()
    assert entries[0]["timestamp"] == ""


def test_append_non_string_timestamp():
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    buf.append({"event": "num-ts", "level": "info", "timestamp": 12345}, "info")
    entries = buf.snapshot_newest_first()
    assert entries[0]["timestamp"] == "12345"


def test_append_with_extra_context():
    """Extra keys beyond event/level become part of message JSON."""
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    buf.append(
        {"event": "with-ctx", "level": "info", "request_id": "abc", "user": "test"},
        "info",
    )
    entries = buf.snapshot_newest_first()
    msg = entries[0]["message"]
    assert "with-ctx" in msg
    assert "abc" in msg
    assert "test" in msg


def test_append_none_event():
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    buf.append({"level": "info"}, "info")
    entries = buf.snapshot_newest_first()
    assert entries[0]["message"] == ""


def test_append_non_string_event():
    """Non-string event is JSON-serialized."""
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    buf.append({"event": {"key": "value"}, "level": "info"}, "info")
    entries = buf.snapshot_newest_first()
    assert "key" in entries[0]["message"]


def test_message_truncation():
    """Messages longer than _MESSAGE_MAX are truncated."""
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    long_msg = "x" * 10000
    buf.append({"event": long_msg, "level": "info"}, "info")
    entries = buf.snapshot_newest_first()
    assert len(entries[0]["message"]) <= 4096
    assert entries[0]["message"].endswith("...")


def test_snapshot_newest_first_ordering():
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    for i in range(5):
        buf.append({"event": f"msg-{i}", "level": "info"}, "info")
    entries = buf.snapshot_newest_first()
    assert "msg-4" in entries[0]["message"]
    assert "msg-0" in entries[-1]["message"]


def test_meta_keys_excluded_from_message():
    """Keys like exc_info, stack_info should not appear in message."""
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    buf.append(
        {
            "event": "clean",
            "level": "error",
            "exc_info": "traceback...",
            "stack_info": "stack...",
            "exception": "RuntimeError",
            "exc_text": "text",
        },
        "error",
    )
    entries = buf.snapshot_newest_first()
    assert "traceback" not in entries[0]["message"]
    assert "stack..." not in entries[0]["message"]


def test_json_dumps_fallback_on_circular_ref():
    """Circular reference in extra context falls back to str() instead of crashing."""
    clear_log_buffer_for_testing()
    buf = get_log_buffer()
    circular: dict = {"event": "circ", "level": "info", "data": {}}
    circular["data"]["self"] = circular["data"]
    buf.append(circular, "info")
    entries = buf.snapshot_newest_first()
    assert len(entries) == 1
    assert entries[0]["message"]
