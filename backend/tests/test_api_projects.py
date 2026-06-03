"""Tests for /api/projects (PROJ-01–PROJ-03)."""

from __future__ import annotations


def test_create_project(client):
    r = client.post("/api/projects", json={"name": "A", "description": "d"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "A"
    assert "value" not in data


def test_list_projects_pagination(client):
    assert client.post("/api/projects", json={"name": "P1", "description": None}).status_code == 201
    assert client.post("/api/projects", json={"name": "P2", "description": None}).status_code == 201
    r = client.get("/api/projects?limit=1&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert len(data["items"]) == 1


def test_get_patch_delete_project(client):
    unknown = "00000000-0000-0000-0000-000000000001"
    r = client.get(f"/api/projects/{unknown}")
    assert r.status_code == 404
    assert r.json()["code"] == "ENTITY_NOT_FOUND"

    create = client.post("/api/projects", json={"name": "X", "description": None})
    assert create.status_code == 201
    pid = create.json()["id"]

    r = client.patch(f"/api/projects/{pid}", json={"name": "Y"})
    assert r.status_code == 200
    assert r.json()["name"] == "Y"

    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204

    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 404
    assert r.json()["code"] == "ENTITY_NOT_FOUND"
