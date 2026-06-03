"""Thread-safe in-memory ring buffer for redacted log lines (D-105)."""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from typing import Any

_MAX_LEN = 1000
_MESSAGE_MAX = 4096

_buffer: deque[dict[str, Any]] | None = None
_lock = threading.Lock()


def get_log_buffer() -> "LogBuffer":
    """Return the process-wide log buffer singleton."""
    global _buffer
    with _lock:
        if _buffer is None:
            _buffer = deque(maxlen=_MAX_LEN)
        return LogBuffer(_buffer)


def clear_log_buffer_for_testing() -> None:
    """Clear all buffered lines (test isolation only)."""
    global _buffer
    with _lock:
        if _buffer is not None:
            _buffer.clear()


class LogBuffer:
    """Ring buffer of log entry dicts (newest appended at end)."""

    def __init__(self, entries: deque[dict[str, Any]]) -> None:
        self._entries = entries
        self._lock = _lock

    def append(self, event_dict: dict[str, Any], method_name: str) -> None:
        """Store one line after redaction; safe from concurrent structlog calls."""
        ts = event_dict.get("timestamp")
        if ts is None:
            ts = ""
        elif not isinstance(ts, str):
            ts = str(ts)

        level_val = event_dict.get("level")
        if isinstance(level_val, int):
            level_str = logging.getLevelName(level_val)
        elif isinstance(level_val, str):
            level_str = level_val.upper()
        else:
            level_str = (method_name or "info").upper()

        source = str(event_dict.get("logger", ""))

        # Payload for the message line: event + bound context (redaction already applied).
        _skip_meta = (
            "timestamp",
            "level",
            "logger",
            "exc_info",
            "stack_info",
            "exception",
            "exc_text",
        )
        rest = {
            k: v
            for k, v in event_dict.items()
            if k not in _skip_meta
        }
        event_msg = rest.pop("event", None)
        if not rest:
            if isinstance(event_msg, str):
                message = event_msg
            elif event_msg is None:
                message = ""
            else:
                message = json.dumps(event_msg, default=str, ensure_ascii=False)
        else:
            body: dict[str, Any] = {}
            if event_msg is not None:
                body["event"] = event_msg
            body.update(rest)
            try:
                message = json.dumps(body, default=str, ensure_ascii=False)
            except (TypeError, ValueError):
                message = str(body)
        if len(message) > _MESSAGE_MAX:
            message = message[: _MESSAGE_MAX - 3] + "..."

        entry = {
            "timestamp": ts,
            "level": level_str,
            "source": source,
            "message": message,
        }
        with self._lock:
            self._entries.append(entry)

    def snapshot_newest_first(self) -> list[dict[str, Any]]:
        """Return a copy of entries with newest first (up to maxlen)."""
        with self._lock:
            return list(reversed(self._entries))
