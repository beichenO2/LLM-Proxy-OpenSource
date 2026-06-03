"""Tests for GET /api/logs (LOGS-01–LOGS-03)."""

from __future__ import annotations

import json

import pytest

from app.logging_config import clear_registered_secrets, get_logger, register_secrets_for_redaction
from app.services.log_buffer import clear_log_buffer_for_testing


@pytest.fixture(autouse=True)
def _reset_logs_buffer() -> None:
    clear_registered_secrets()
    clear_log_buffer_for_testing()
    yield
    clear_registered_secrets()
    clear_log_buffer_for_testing()


def test_get_logs_returns_redacted_probe(client) -> None:
    token = "logs-probe-redact-token-9c1e"
    register_secrets_for_redaction([token])
    log = get_logger("tests.log_buffer_probe")
    log.info("log_buffer_probe_event", probe_field=token)

    r = client.get("/api/logs", params={"q": "log_buffer"})
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    blob = json.dumps(data["items"])
    assert token not in blob
    assert "[REDACTED]" in blob


def test_get_logs_filters_level_source_limit(client) -> None:
    log_a = get_logger("tests.source.alpha")
    log_b = get_logger("tests.source.beta")
    log_a.warning("warn_marker_unique_xyz")
    log_b.info("info_marker_unique_xyz")

    r = client.get(
        "/api/logs",
        params={"level": "WARN", "q": "marker_unique", "limit": 10},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    assert all(
        "WARN" in it["level"].upper() or "ERROR" in it["level"].upper()
        for it in items
    )
    assert any("warn_marker" in it["message"].lower() for it in items)

    r2 = client.get("/api/logs", params={"source": "beta", "q": "marker"})
    assert r2.status_code == 200
    items2 = r2.json()["items"]
    assert len(items2) >= 1
    assert all("beta" in it["source"] for it in items2)


def test_get_logs_q_filter_excludes_non_matching(client) -> None:
    """Logs that don't match the q filter are excluded from results."""
    log = get_logger("tests.q_filter")
    log.info("matching_needle_abc")
    log.info("unrelated_noise_xyz")

    r = client.get("/api/logs", params={"q": "matching_needle"})
    assert r.status_code == 200
    items = r.json()["items"]
    for item in items:
        assert "matching_needle" in item["message"].lower()
    assert not any("unrelated_noise" in it["message"].lower() for it in items)
