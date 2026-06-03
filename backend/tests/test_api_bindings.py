"""Tests for /api/bindings (BIND-01–BIND-04, D-29)."""

from __future__ import annotations


def test_create_binding(client):
    r = client.post(
        "/api/bindings",
        json={
            "service_name": "service.llm.chat",
            "secret_ref_key": "secret.openai.default",
            "project_id": None,
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["secret_ref_key"] == "secret.openai.default"
    assert data["service_name"] == "service.llm.chat"
    assert "resolved" in data


def test_resolved_true_when_secret_exists(client):
    assert (
        client.post(
            "/api/secrets",
            json={
                "key": "secret.openai.default",
                "value": "sk-test",
                "project_id": None,
            },
        ).status_code
        == 201
    )
    create_b = client.post(
        "/api/bindings",
        json={
            "service_name": "service.resolved.true",
            "secret_ref_key": "secret.openai.default",
            "project_id": None,
        },
    )
    assert create_b.status_code == 201
    bid = create_b.json()["id"]

    r = client.get("/api/bindings")
    assert r.status_code == 200
    match = next(x for x in r.json()["items"] if x["id"] == bid)
    assert match["resolved"] is True


def test_resolved_false_when_disabled(client):
    sec = client.post(
        "/api/secrets",
        json={
            "key": "secret.binding.disabled.test",
            "value": "x",
            "project_id": None,
        },
    )
    assert sec.status_code == 201
    sid = sec.json()["id"]

    create_b = client.post(
        "/api/bindings",
        json={
            "service_name": "service.disabled.probe",
            "secret_ref_key": "secret.binding.disabled.test",
            "project_id": None,
        },
    )
    assert create_b.status_code == 201
    bid = create_b.json()["id"]

    assert client.get(f"/api/bindings/{bid}").json()["resolved"] is True

    assert client.patch(f"/api/secrets/{sid}", json={"enabled": False}).status_code == 200

    r = client.get(f"/api/bindings/{bid}")
    assert r.status_code == 200
    assert r.json()["resolved"] is False


def test_binding_json_has_no_value_field(client):
    create = client.post(
        "/api/bindings",
        json={
            "service_name": "service.no.value.field",
            "secret_ref_key": "secret.placeholder.binding",
            "project_id": None,
        },
    )
    assert create.status_code == 201
    bid = create.json()["id"]

    r = client.get("/api/bindings")
    assert r.status_code == 200
    row = next(x for x in r.json()["items"] if x["id"] == bid)
    assert "value" not in row


def test_patch_delete_binding(client):
    create = client.post(
        "/api/bindings",
        json={
            "service_name": "service.patch.target",
            "secret_ref_key": "secret.patch.ref",
            "project_id": None,
        },
    )
    assert create.status_code == 201
    bid = create.json()["id"]

    r = client.patch(f"/api/bindings/{bid}", json={"service_name": "service.patch.updated"})
    assert r.status_code == 200
    assert r.json()["service_name"] == "service.patch.updated"

    r = client.delete(f"/api/bindings/{bid}")
    assert r.status_code == 204


def test_create_binding_auth_header_round_trip(client):
    create = client.post(
        "/api/bindings",
        json={
            "service_name": "service.auth.header.test",
            "secret_ref_key": "secret.auth.header.ref",
            "project_id": None,
            "auth_header": "X-API-Key",
        },
    )
    assert create.status_code == 201
    bid = create.json()["id"]
    assert create.json()["auth_header"] == "X-API-Key"

    r = client.get(f"/api/bindings/{bid}")
    assert r.status_code == 200
    assert r.json()["auth_header"] == "X-API-Key"


def test_create_binding_omits_auth_header_is_null(client):
    create = client.post(
        "/api/bindings",
        json={
            "service_name": "service.no.auth.header",
            "secret_ref_key": "secret.no.auth.header",
            "project_id": None,
        },
    )
    assert create.status_code == 201
    assert create.json()["auth_header"] is None
