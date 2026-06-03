"""Tests for GET /api/sanitize/mappings endpoint."""

from __future__ import annotations

from starlette.testclient import TestClient


def _seed_secrets(client: TestClient, project_id: str | None = None) -> None:
    for key, value in [
        ("secret.openai.api_key", "sk-test-12345"),
        ("secret.aliyun.api_key", "sk-aliyun-67890"),
    ]:
        body: dict = {"key": key, "value": value}
        if project_id:
            body["project_id"] = project_id
        client.post("/api/secrets", json=body)


def test_get_mappings_empty(client: TestClient) -> None:
    resp = client.get("/api/sanitize/mappings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["secrets"] == []
    assert "version" in data


def test_get_mappings_with_data(client: TestClient) -> None:
    _seed_secrets(client)

    resp = client.get("/api/sanitize/mappings")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["secrets"]) == 2
    sec_keys = {s["key"] for s in data["secrets"]}
    assert "secret.openai.api_key" in sec_keys
    for s in data["secrets"]:
        assert "value" not in s


def test_get_mappings_filter_by_project(client: TestClient) -> None:
    proj = client.post("/api/projects", json={"name": "TestProject"}).json()
    pid = proj["id"]

    _seed_secrets(client, project_id=pid)
    _seed_secrets(client)

    resp = client.get(f"/api/sanitize/mappings?project_id={pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["secrets"]) == 2
    for s in data["secrets"]:
        assert s["project_id"] == pid


def test_mappings_excludes_disabled_secrets(client: TestClient) -> None:
    _seed_secrets(client)

    resp = client.get("/api/secrets")
    secret_id = resp.json()["items"][0]["id"]
    client.patch(f"/api/secrets/{secret_id}", json={"enabled": False})

    resp = client.get("/api/sanitize/mappings")
    data = resp.json()
    assert len(data["secrets"]) == 1
