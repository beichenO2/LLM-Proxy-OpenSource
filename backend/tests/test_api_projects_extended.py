"""Extended project API tests — patch description, delete 404, edge cases."""

from __future__ import annotations


def test_patch_project_description(client):
    create = client.post("/api/projects", json={"name": "Desc Test", "description": "old"})
    assert create.status_code == 201
    pid = create.json()["id"]

    r = client.patch(f"/api/projects/{pid}", json={"description": "new description"})
    assert r.status_code == 200
    assert r.json()["description"] == "new description"


def test_patch_project_not_found(client):
    r = client.patch("/api/projects/nonexistent-id", json={"name": "X"})
    assert r.status_code == 404
    assert r.json()["code"] == "ENTITY_NOT_FOUND"


def test_delete_project_not_found(client):
    r = client.delete("/api/projects/nonexistent-id")
    assert r.status_code == 404
    assert r.json()["code"] == "ENTITY_NOT_FOUND"


def test_get_project_by_id(client):
    create = client.post("/api/projects", json={"name": "Get By ID", "description": "test"})
    assert create.status_code == 201
    pid = create.json()["id"]
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Get By ID"
    assert r.json()["description"] == "test"


def test_patch_project_name_and_description(client):
    """Patching both name and description in one request."""
    create = client.post("/api/projects", json={"name": "Both Test"})
    assert create.status_code == 201
    pid = create.json()["id"]
    r = client.patch(f"/api/projects/{pid}", json={"name": "Both Updated", "description": "added desc"})
    assert r.status_code == 200
    assert r.json()["name"] == "Both Updated"
    assert r.json()["description"] == "added desc"


def test_patch_project_null_name_rejected(client):
    """Explicitly setting name to null should be rejected with 422."""
    create = client.post("/api/projects", json={"name": "Null Name Test"})
    assert create.status_code == 201
    pid = create.json()["id"]
    r = client.patch(f"/api/projects/{pid}", json={"name": None})
    assert r.status_code == 422
    assert "null" in r.json()["detail"].lower() or "VALIDATION_ERROR" in str(r.json())
