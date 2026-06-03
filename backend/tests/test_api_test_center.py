"""Tests for POST /api/test-center/run — LLM connectivity testing."""

from __future__ import annotations


def test_llm_connectivity_no_bindings(client):
    """LLM connectivity test with no bindings returns fail/skip."""
    r = client.post(
        "/api/test-center/run",
        json={"test_type": "llm_connectivity"},
    )
    assert r.status_code == 200
    data = r.json()
    for item in data["results"]:
        assert item["status"] in ("pass", "fail", "skip")


def test_llm_connectivity_with_registered_service(client):
    """LLM connectivity test checks registered services from MODEL_SERVICE_MAP."""
    # Create a secret and binding for a registered service
    r = client.post(
        "/api/secrets",
        json={"key": "secret.llm.test", "value": "test-val", "project_id": None, "base_url": "https://api.example.com"},
    )
    assert r.status_code == 201

    # Create binding for a registered service name
    r = client.post(
        "/api/bindings",
        json={"service_name": "llm.minimax", "secret_ref_key": "secret.llm.test", "project_id": None},
    )
    assert r.status_code == 201

    r = client.post(
        "/api/test-center/run",
        json={"test_type": "llm_connectivity"},
    )
    assert r.status_code == 200
    results = r.json()["results"]
    # Should have results for registered services
    assert len(results) > 0
    for item in results:
        assert item["status"] in ("pass", "fail", "skip")
        assert item["name"].startswith("llm:")


def test_llm_connectivity_fail_disabled_secret(client):
    """LLM connectivity test fails when secret is disabled."""
    r = client.post(
        "/api/secrets",
        json={"key": "secret.llm.disabled", "value": "test-val", "project_id": None, "base_url": "https://api.example.com"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]

    # Disable the secret
    r = client.patch(f"/api/secrets/{sid}", json={"enabled": False})
    assert r.status_code == 200

    # Create binding for a registered service
    r = client.post(
        "/api/bindings",
        json={"service_name": "llm.minimax", "secret_ref_key": "secret.llm.disabled", "project_id": None},
    )
    assert r.status_code == 201

    r = client.post(
        "/api/test-center/run",
        json={"test_type": "llm_connectivity"},
    )
    assert r.status_code == 200
    results = r.json()["results"]
    # Find the minimax result
    minimax_items = [x for x in results if "llm.minimax" in x["name"]]
    assert len(minimax_items) == 1
    assert minimax_items[0]["status"] == "fail"
    assert "disabled" in minimax_items[0]["message"].lower()


def test_llm_connectivity_fail_no_base_url(client):
    """LLM connectivity test fails when secret has no base_url."""
    r = client.post(
        "/api/secrets",
        json={"key": "secret.llm.nourl", "value": "test-val", "project_id": None, "base_url": None},
    )
    assert r.status_code == 201

    r = client.post(
        "/api/bindings",
        json={"service_name": "llm.minimax", "secret_ref_key": "secret.llm.nourl", "project_id": None},
    )
    assert r.status_code == 201

    r = client.post(
        "/api/test-center/run",
        json={"test_type": "llm_connectivity"},
    )
    assert r.status_code == 200
    results = r.json()["results"]
    nourl_items = [x for x in results if "llm.minimax" in x["name"]]
    assert len(nourl_items) == 1
    assert nourl_items[0]["status"] == "fail"
    assert "base_url" in nourl_items[0]["message"].lower()


def test_llm_connectivity_fail_missing_secret(client):
    """LLM connectivity test fails when secret referenced by binding does not exist."""
    r = client.post(
        "/api/bindings",
        json={"service_name": "llm.minimax", "secret_ref_key": "secret.nonexistent", "project_id": None},
    )
    assert r.status_code == 201

    r = client.post(
        "/api/test-center/run",
        json={"test_type": "llm_connectivity"},
    )
    assert r.status_code == 200
    results = r.json()["results"]
    missing_items = [x for x in results if "llm.minimax" in x["name"]]
    assert len(missing_items) == 1
    assert missing_items[0]["status"] == "fail"


def test_llm_status_endpoint(client):
    """GET /api/test-center/llm-status returns service status."""
    r = client.get("/api/test-center/llm-status")
    assert r.status_code == 200
    data = r.json()
    assert "services" in data
    assert isinstance(data["services"], list)


def test_llm_status_updates_after_connectivity_test(client):
    """LLM status is updated after connectivity test."""
    # Create secret and binding
    r = client.post(
        "/api/secrets",
        json={"key": "secret.llm.status", "value": "test-val", "project_id": None, "base_url": "https://api.example.com"},
    )
    assert r.status_code == 201

    r = client.post(
        "/api/bindings",
        json={"service_name": "llm.minimax", "secret_ref_key": "secret.llm.status", "project_id": None},
    )
    assert r.status_code == 201

    # Run connectivity test
    r = client.post(
        "/api/test-center/run",
        json={"test_type": "llm_connectivity"},
    )
    assert r.status_code == 200

    # Check LLM status was updated
    r = client.get("/api/test-center/llm-status")
    assert r.status_code == 200
    services = r.json()["services"]
    minimax_service = next((s for s in services if s["service_name"] == "llm.minimax"), None)
    assert minimax_service is not None
    # Should have been called (status is not None)
    assert minimax_service["last_call_status"] is not None
