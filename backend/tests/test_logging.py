"""SCRT-08: registered secrets must not appear in structured or stdlib log output."""

from __future__ import annotations

import io
import logging

import pytest
import structlog

from app.logging_config import (
    clear_registered_secrets,
    configure_logging,
    register_secrets_for_redaction,
)

SECRET = "SUPER_SECRET_TOKEN_999"


@pytest.fixture(autouse=True)
def _logging_isolation() -> None:
    clear_registered_secrets()
    configure_logging()
    yield
    clear_registered_secrets()


def _with_capture() -> tuple[io.StringIO, logging.Handler]:
    root = logging.getLogger()
    buf = io.StringIO()
    extra = logging.StreamHandler(buf)
    extra.setFormatter(root.handlers[0].formatter)
    root.addHandler(extra)
    return buf, extra


def test_log_redaction() -> None:
    register_secrets_for_redaction([SECRET])
    buf, extra = _with_capture()
    try:
        structlog.get_logger("test.struct").info("before SUPER_SECRET_TOKEN_999 after")
        out = buf.getvalue()
    finally:
        logging.getLogger().removeHandler(extra)
    assert "[REDACTED]" in out
    assert SECRET not in out


def test_stdlib_logger_redacted() -> None:
    register_secrets_for_redaction([SECRET])
    buf, extra = _with_capture()
    try:
        logging.getLogger("third.party").info("token=SUPER_SECRET_TOKEN_999")
        out = buf.getvalue()
    finally:
        logging.getLogger().removeHandler(extra)
    assert "[REDACTED]" in out
    assert SECRET not in out
