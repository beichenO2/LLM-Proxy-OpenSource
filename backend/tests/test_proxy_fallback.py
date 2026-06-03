"""Tests for R10: Fallback chain support in LLM Proxy."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Binding, Secret


def test_binding_fallback_fields_exist(client: TestClient) -> None:
    """Test that Binding model has fallback fields."""
    # This is implicitly tested by the API working
    # Just verify the model has the expected attributes
    from app.db.models import Binding
    assert hasattr(Binding, "fallback_chain")
    assert hasattr(Binding, "priority")
    assert hasattr(Binding, "cooldown_until")
    assert hasattr(Binding, "consecutive_failures")


def test_set_fallback_chain(client: TestClient, db_session) -> None:
    """Test setting fallback chain for a binding."""
    # Create two bindings
    resp1 = client.post("/api/bindings", json={
        "service_name": "llm.primary",
        "secret_ref_key": "test.key1",
    })
    assert resp1.status_code == 201
    binding1_id = resp1.json()["id"]

    resp2 = client.post("/api/bindings", json={
        "service_name": "llm.backup",
        "secret_ref_key": "test.key2",
    })
    assert resp2.status_code == 201

    # Set fallback chain
    resp = client.put(f"/api/bindings/{binding1_id}/fallback", json={
        "fallback_chain": ["llm.backup"],
        "priority": 3,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["fallback_chain"] == ["llm.backup"]
    assert data["priority"] == 3


def test_get_fallback_chain(client: TestClient, db_session) -> None:
    """Test getting fallback chain configuration."""
    # Create binding
    resp = client.post("/api/bindings", json={
        "service_name": "llm.test",
        "secret_ref_key": "test.key",
    })
    assert resp.status_code == 201
    binding_id = resp.json()["id"]

    # Get fallback (should be empty)
    resp = client.get(f"/api/bindings/{binding_id}/fallback")
    assert resp.status_code == 200
    data = resp.json()
    assert data["fallback_chain"] is None
    assert data["priority"] == 1


def test_get_binding_status(client: TestClient, db_session) -> None:
    """Test getting binding runtime status."""
    resp = client.post("/api/bindings", json={
        "service_name": "llm.status-test",
        "secret_ref_key": "test.key",
    })
    assert resp.status_code == 201
    binding_id = resp.json()["id"]

    resp = client.get(f"/api/bindings/{binding_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service_name"] == "llm.status-test"
    assert data["is_cooling_down"] is False
    assert data["consecutive_failures"] == 0


def test_reset_cooldown(client: TestClient, db_session) -> None:
    """Test manually resetting cooldown."""
    resp = client.post("/api/bindings", json={
        "service_name": "llm.cooldown-test",
        "secret_ref_key": "test.key",
    })
    assert resp.status_code == 201
    binding_id = resp.json()["id"]

    # Set cooldown manually
    binding = db_session.get(Binding, binding_id)
    binding.cooldown_until = datetime.utcnow() + timedelta(minutes=5)
    binding.consecutive_failures = 3
    db_session.flush()

    # Reset cooldown
    resp = client.post(f"/api/bindings/{binding_id}/reset-cooldown")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["cooldown_until"] is None
    assert data["consecutive_failures"] == 0


def test_circular_fallback_prevented(client: TestClient, db_session) -> None:
    """Test that binding cannot fallback to itself."""
    resp = client.post("/api/bindings", json={
        "service_name": "llm.circular",
        "secret_ref_key": "test.key",
    })
    assert resp.status_code == 201
    binding_id = resp.json()["id"]

    # Try to set circular fallback
    resp = client.put(f"/api/bindings/{binding_id}/fallback", json={
        "fallback_chain": ["llm.circular"],
    })
    assert resp.status_code == 400
    assert "CIRCULAR_FALLBACK" in resp.text


def test_fallback_to_nonexistent_binding(client: TestClient, db_session) -> None:
    """Test that fallback to non-existent binding is rejected."""
    resp = client.post("/api/bindings", json={
        "service_name": "llm.primary",
        "secret_ref_key": "test.key",
    })
    assert resp.status_code == 201
    binding_id = resp.json()["id"]

    resp = client.put(f"/api/bindings/{binding_id}/fallback", json={
        "fallback_chain": ["llm.nonexistent"],
    })
    assert resp.status_code == 400
    assert "FALLBACK_BINDING_NOT_FOUND" in resp.text


def test_resolve_fallback_chain_excludes_cooling(db_session) -> None:
    """Test that _resolve_fallback_chain excludes bindings in cooldown."""
    from app.api.proxy import _resolve_fallback_chain, _set_binding_cooldown

    # Create bindings
    primary = Binding(
        id="primary-id",
        service_name="llm.primary",
        secret_ref_key="test.key1",
        fallback_chain='["llm.backup1", "llm.backup2"]',
        priority=1,
        consecutive_failures=0,
    )
    backup1 = Binding(
        id="backup1-id",
        service_name="llm.backup1",
        secret_ref_key="test.key2",
        priority=1,
        consecutive_failures=0,
    )
    backup2 = Binding(
        id="backup2-id",
        service_name="llm.backup2",
        secret_ref_key="test.key3",
        priority=1,
        consecutive_failures=0,
    )

    db_session.add_all([primary, backup1, backup2])
    db_session.flush()

    # Put backup1 in cooldown
    _set_binding_cooldown(backup1, seconds=60)
    db_session.flush()

    # Resolve chain - should exclude backup1
    chain = _resolve_fallback_chain(db_session, primary)
    service_names = [b.service_name for b in chain]
    assert "llm.primary" in service_names
    assert "llm.backup1" not in service_names  # In cooldown
    assert "llm.backup2" in service_names


def test_should_trigger_fallback() -> None:
    """Test _should_trigger_fallback returns correct values."""
    from app.api.proxy import _should_trigger_fallback

    # Should trigger fallback
    assert _should_trigger_fallback(429) is True
    assert _should_trigger_fallback(500) is True
    assert _should_trigger_fallback(502) is True
    assert _should_trigger_fallback(503) is True
    assert _should_trigger_fallback(504) is True

    # Should NOT trigger fallback
    assert _should_trigger_fallback(400) is False
    assert _should_trigger_fallback(401) is False
    assert _should_trigger_fallback(403) is False
    assert _should_trigger_fallback(404) is False
    assert _should_trigger_fallback(200) is False


def test_is_cooling_down(db_session) -> None:
    """Test _is_cooling_down helper."""
    from app.api.proxy import _is_cooling_down

    binding = Binding(
        id="test-id",
        service_name="llm.test",
        secret_ref_key="test.key",
        priority=1,
        consecutive_failures=0,
    )
    db_session.add(binding)
    db_session.flush()

    # No cooldown
    assert _is_cooling_down(binding) is False

    # Future cooldown
    binding.cooldown_until = datetime.utcnow() + timedelta(minutes=5)
    assert _is_cooling_down(binding) is True

    # Past cooldown
    binding.cooldown_until = datetime.utcnow() - timedelta(minutes=5)
    assert _is_cooling_down(binding) is False
