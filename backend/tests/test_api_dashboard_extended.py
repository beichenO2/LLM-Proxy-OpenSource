"""Extended dashboard tests — project_id filtering, summary with data."""

from __future__ import annotations


def test_dashboard_summary_with_project_id(client):
    """Summary filtered by project_id returns scoped counts."""
    proj = client.post("/api/projects", json={"name": "Dashboard Proj"})
    assert proj.status_code == 201
    pid = proj.json()["id"]

    client.post("/api/secrets", json={
        "key": "secret.dash.test",
        "value": "val",
        "project_id": pid,
    })
    r = client.get(f"/api/dashboard/summary?project_id={pid}")
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == pid
    assert data["secret_count"] >= 1


def test_audit_log_filter_by_project_id(client):
    """Audit log filtered by project_id returns only matching entries."""
    proj = client.post("/api/projects", json={"name": "Audit Filter Proj"})
    assert proj.status_code == 201
    pid = proj.json()["id"]

    r = client.get(f"/api/audit-log?project_id={pid}")
    assert r.status_code == 200
    data = r.json()
    for item in data["items"]:
        assert item["project_id"] == pid


def test_audit_log_with_limit(client):
    """Audit log respects limit parameter."""
    for i in range(3):
        client.post("/api/projects", json={"name": f"LimitProj{i}"})

    r = client.get("/api/audit-log?limit=1")
    assert r.status_code == 200
    assert len(r.json()["items"]) <= 1
