"""Tests for /api/dashboard/summary and /api/audit-log."""

from __future__ import annotations


def test_dashboard_summary_returns_integer_counts(client):
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data["secret_count"], int)
    assert isinstance(data["binding_count"], int)
    assert "project_id" in data


def test_audit_log_returns_items_list(client):
    r = client.get("/api/audit-log")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_audit_log_records_project_create(client):
    assert (
        client.post("/api/projects", json={"name": "AuditProj", "description": None}).status_code
        == 201
    )
    r = client.get("/api/audit-log")
    assert r.status_code == 200
    actions = [item["action"] for item in r.json()["items"]]
    assert "project.create" in actions
    assert any("project" in a for a in actions)
