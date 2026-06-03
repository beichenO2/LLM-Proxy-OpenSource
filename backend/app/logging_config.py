"""Central structlog configuration with secret substring redaction (D-10, D-11, D-12).

Registered secrets are replaced with the literal ``[REDACTED]``. Replacements use
longest substrings first to avoid partial leaks when one secret is a prefix of another.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable
from typing import Any, cast

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer, StackInfoRenderer, TimeStamper
from structlog.typing import EventDict, Processor, WrappedLogger

# Module-level registry of secret substrings to scrub from log event payloads.
_REDACTION_SUBSTRINGS: set[str] = set()

def register_secrets_for_redaction(values: Iterable[str]) -> None:
    """Add non-empty strings to the global redaction set."""
    for v in values:
        if v:
            _REDACTION_SUBSTRINGS.add(v)


def clear_registered_secrets() -> None:
    """Clear all registered secret substrings (for test isolation)."""
    _REDACTION_SUBSTRINGS.clear()


def _redact_string(text: str) -> str:
    if not _REDACTION_SUBSTRINGS:
        return text
    for secret in sorted(_REDACTION_SUBSTRINGS, key=len, reverse=True):
        if secret in text:
            text = text.replace(secret, "[REDACTED]")
    return text


# OpenAI-style key shape — scrub even when not in the registered set (TEST-05, D-102).
_SK_LIKE_PATTERN = re.compile(r"sk-[a-zA-Z0-9_-]{10,}")


def sanitize_user_facing_string(text: str) -> str:
    """Registered-secret redaction plus API-key-like substring scrubbing for UI/test output."""
    s = _redact_string(text)
    return _SK_LIKE_PATTERN.sub("[REDACTED]", s)


def _redact_value(obj: Any) -> Any:
    if isinstance(obj, str):
        return _redact_string(obj)
    if isinstance(obj, bytes):
        try:
            decoded = obj.decode("utf-8", errors="replace")
            redacted = _redact_string(decoded)
            return redacted.encode("utf-8") if redacted != decoded else obj
        except Exception:
            return obj
    if isinstance(obj, dict):
        return {k: _redact_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        result = [_redact_value(x) for x in obj]
        return type(obj)(result) if isinstance(obj, tuple) else result
    return obj


def redact_processor(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Recursively redact registered secret substrings in string leaves of *event_dict*."""
    if not _REDACTION_SUBSTRINGS:
        return event_dict
    return cast(EventDict, _redact_value(event_dict))


def _buffer_log_processor(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Append redacted event to in-memory ring buffer; must run after ``redact_processor``."""
    # Lazy import avoids circular import via app.services.__init__ → vault → logging_config
    from app.services.log_buffer import get_log_buffer

    get_log_buffer().append(dict(event_dict), method_name)
    return event_dict


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a stdlib-backed structlog logger."""
    return structlog.get_logger(name)


def configure_logging(json_format: bool = False) -> None:
    """Configure structlog + stdlib logging with shared redaction. Safe to call twice."""
    timestamper = TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        StackInfoRenderer(),
        timestamper,
        redact_processor,
        _buffer_log_processor,
    ]

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: Processor
    if json_format:
        renderer = JSONRenderer()
    else:
        renderer = ConsoleRenderer(colors=False)

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            StackInfoRenderer(),
            timestamper,
            redact_processor,
            _buffer_log_processor,
        ],
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.NOTSET)
    handler.setFormatter(formatter)
    root.addHandler(handler)
