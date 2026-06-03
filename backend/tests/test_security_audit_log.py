"""Security tests: audit log must never contain secret values."""

from __future__ import annotations


def test_audit_log_secret_create_does_not_contain_value(client):
    """audit_log entry for secret.create must not contain the secret value."""
    client.post(
        "/api/secrets",
        json={
            "key": "secret.audit.probe",
            "value": "sk-AUDIT-PROBE-SECRET-VALUE-9999",
            "project_id": None,
        },
    )

    r = client.get("/api/audit-log?limit=200")
    assert r.status_code == 200
    for item in r.json()["items"]:
        detail = item.get("detail") or ""
        assert "sk-AUDIT-PROBE" not in detail, (
            "audit log must never contain secret value"
        )
        assert "AUDIT-PROBE-SECRET" not in detail


def test_audit_log_vault_unlock_does_not_contain_password(client):
    """audit_log entry for vault.unlock must not contain the master password."""
    r = client.get("/api/audit-log?limit=200")
    assert r.status_code == 200
    for item in r.json()["items"]:
        if item["action"] == "vault.unlock":
            detail = item.get("detail")
            assert detail is None or "password" not in detail.lower()
