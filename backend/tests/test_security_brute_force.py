"""Security tests: vault unlock brute-force protection."""

from __future__ import annotations

from app.api import vault_routes


def test_vault_unlock_rate_limits_after_failures(client, monkeypatch):
    """After _MAX_FAILURES wrong attempts, unlock returns 429."""
    monkeypatch.setattr(vault_routes, "_MAX_FAILURES", 3)
    monkeypatch.setattr(vault_routes, "_LOCKOUT_SECONDS", 5)

    with vault_routes._fail_lock:
        vault_routes._fail_count = 0
        vault_routes._lockout_until = 0.0

    for _ in range(3):
        r = client.post(
            "/api/vault/unlock", json={"master_password": "wrong-password"}
        )
        assert r.status_code == 401

    r = client.post(
        "/api/vault/unlock", json={"master_password": "wrong-password"}
    )
    assert r.status_code == 429
    assert r.json()["code"] == "RATE_LIMITED"

    with vault_routes._fail_lock:
        vault_routes._fail_count = 0
        vault_routes._lockout_until = 0.0


def test_vault_unlock_resets_count_on_success(client, monkeypatch):
    """Successful unlock resets the failure counter."""
    monkeypatch.setattr(vault_routes, "_MAX_FAILURES", 3)

    with vault_routes._fail_lock:
        vault_routes._fail_count = 0
        vault_routes._lockout_until = 0.0

    client.post("/api/vault/unlock", json={"master_password": "wrong"})
    assert vault_routes._fail_count == 1

    r = client.post(
        "/api/vault/unlock", json={"master_password": "test-master-password"}
    )
    assert r.status_code == 200
    assert vault_routes._fail_count == 0
