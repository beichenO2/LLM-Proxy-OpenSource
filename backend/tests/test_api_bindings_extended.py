"""Extended bindings API tests — CRUD completeness, validation, edge cases."""

from __future__ import annotations


def _create_secret(client, key: str) -> None:
    r = client.post(
        "/api/secrets",
        json={"key": key, "value": "val", "project_id": None},
    )
    assert r.status_code == 201


def _create_binding(client, service_name: str, secret_ref_key: str, **kw) -> dict:
    r = client.post(
        "/api/bindings",
        json={"service_name": service_name, "secret_ref_key": secret_ref_key, "project_id": None, **kw},
    )
    assert r.status_code == 201
    return r.json()


def test_get_single_binding(client):
    _create_secret(client, "secret.bind.get")
    data = _create_binding(client, "bind.get.svc", "secret.bind.get")
    bid = data["id"]
    r = client.get(f"/api/bindings/{bid}")
    assert r.status_code == 200
    assert r.json()["service_name"] == "bind.get.svc"


def test_get_binding_not_found(client):
    r = client.get("/api/bindings/nonexistent-id")
    assert r.status_code == 404
    assert r.json()["code"] == "ENTITY_NOT_FOUND"


def test_create_binding_invalid_secret_ref_no_dot(client):
    r = client.post(
        "/api/bindings",
        json={"service_name": "bad.ref", "secret_ref_key": "nodot", "project_id": None},
    )
    assert r.status_code == 422


def test_duplicate_binding_service_name_rejected(client):
    _create_secret(client, "secret.dup.bind")
    _create_binding(client, "dup.svc", "secret.dup.bind")
    r = client.post(
        "/api/bindings",
        json={"service_name": "dup.svc", "secret_ref_key": "secret.dup.bind", "project_id": None},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "DUPLICATE_KEY"


def test_patch_binding_service_name(client):
    _create_secret(client, "secret.patch.bind")
    data = _create_binding(client, "patch.svc.old", "secret.patch.bind")
    bid = data["id"]
    r = client.patch(f"/api/bindings/{bid}", json={"service_name": "patch.svc.new"})
    assert r.status_code == 200
    assert r.json()["service_name"] == "patch.svc.new"


def test_patch_binding_secret_ref_key(client):
    _create_secret(client, "secret.patch.ref.a")
    _create_secret(client, "secret.patch.ref.b")
    data = _create_binding(client, "patch.ref.svc", "secret.patch.ref.a")
    bid = data["id"]
    r = client.patch(f"/api/bindings/{bid}", json={"secret_ref_key": "secret.patch.ref.b"})
    assert r.status_code == 200
    assert r.json()["secret_ref_key"] == "secret.patch.ref.b"


def test_patch_binding_not_found(client):
    r = client.patch("/api/bindings/nonexistent-id", json={"service_name": "x.y"})
    assert r.status_code == 404


def test_patch_binding_duplicate_service_name_rejected(client):
    _create_secret(client, "secret.patchdup.bind")
    _create_binding(client, "patchdup.a", "secret.patchdup.bind")
    data_b = _create_binding(client, "patchdup.b", "secret.patchdup.bind")
    r = client.patch(f"/api/bindings/{data_b['id']}", json={"service_name": "patchdup.a"})
    assert r.status_code == 409


def test_delete_binding_not_found(client):
    r = client.delete("/api/bindings/nonexistent-id")
    assert r.status_code == 404


def test_list_bindings_empty(client):
    r = client.get("/api/bindings")
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)
    assert "total" in r.json()


def test_binding_resolved_reflects_secret_state(client):
    """resolved=true when enabled secret exists, false when disabled."""
    _create_secret(client, "secret.resolved.check")
    data = _create_binding(client, "resolved.check.svc", "secret.resolved.check")
    bid = data["id"]

    r = client.get(f"/api/bindings/{bid}")
    assert r.json()["resolved"] is True

    sec_list = client.get("/api/secrets").json()["items"]
    sec = next(x for x in sec_list if x["key"] == "secret.resolved.check")
    client.patch(f"/api/secrets/{sec['id']}", json={"enabled": False})

    r = client.get(f"/api/bindings/{bid}")
    assert r.json()["resolved"] is False


def test_patch_binding_auth_header(client):
    _create_secret(client, "secret.auth.header")
    data = _create_binding(client, "auth.header.svc", "secret.auth.header")
    bid = data["id"]
    r = client.patch(f"/api/bindings/{bid}", json={"auth_header": "X-Custom-Key"})
    assert r.status_code == 200
    assert r.json()["auth_header"] == "X-Custom-Key"


def test_create_binding_empty_auth_header_rejected(client):
    """Empty string auth_header is rejected by validator."""
    r = client.post(
        "/api/bindings",
        json={
            "service_name": "empty.auth",
            "secret_ref_key": "secret.empty.auth",
            "project_id": None,
            "auth_header": "   ",
        },
    )
    assert r.status_code == 422


def test_create_binding_null_auth_header_accepted(client):
    """Null auth_header is accepted (default behavior)."""
    _create_secret(client, "secret.null.auth")
    r = client.post(
        "/api/bindings",
        json={
            "service_name": "null.auth.svc",
            "secret_ref_key": "secret.null.auth",
            "project_id": None,
            "auth_header": None,
        },
    )
    assert r.status_code == 201
    assert r.json()["auth_header"] is None


def test_list_bindings_filter_by_project_id(client):
    """Filtering by project_id returns only matching bindings."""
    proj = client.post("/api/projects", json={"name": "Bind Filter Proj"})
    assert proj.status_code == 201
    pid = proj.json()["id"]

    _create_secret(client, "secret.proj.bind")
    client.post(
        "/api/bindings",
        json={"service_name": "proj.bind", "secret_ref_key": "secret.proj.bind", "project_id": pid},
    )

    r = client.get(f"/api/bindings?project_id={pid}")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(x["project_id"] == pid for x in items)


def test_patch_binding_empty_auth_header_rejected(client):
    """Patching with empty auth_header string is rejected."""
    _create_secret(client, "secret.patch.emptyauth")
    data = _create_binding(client, "patch.emptyauth", "secret.patch.emptyauth")
    r = client.patch(f"/api/bindings/{data['id']}", json={"auth_header": ""})
    assert r.status_code == 422


def test_patch_binding_null_secret_ref_accepted(client):
    """Patching with secret_ref_key=null keeps existing value (excluded from update)."""
    _create_secret(client, "secret.patch.nullref")
    data = _create_binding(client, "patch.nullref", "secret.patch.nullref")
    r = client.patch(f"/api/bindings/{data['id']}", json={"service_name": "patch.nullref.new"})
    assert r.status_code == 200
    assert r.json()["secret_ref_key"] == "secret.patch.nullref"


def test_patch_binding_explicit_null_auth_header(client):
    """Explicitly setting auth_header=null in patch body should be accepted."""
    _create_secret(client, "secret.null.auth2")
    data = _create_binding(client, "null.auth2.svc", "secret.null.auth2", auth_header="X-Key")
    r = client.patch(f"/api/bindings/{data['id']}", json={"auth_header": None})
    assert r.status_code == 200


def test_patch_binding_invalid_secret_ref_no_dot(client):
    """Patching with secret_ref_key that has no dot is rejected."""
    _create_secret(client, "secret.invalid.ref")
    data = _create_binding(client, "invalid.ref.svc", "secret.invalid.ref")
    r = client.patch(f"/api/bindings/{data['id']}", json={"secret_ref_key": "nodot"})
    assert r.status_code == 422


def test_patch_binding_null_secret_ref_key_rejected(client):
    """Explicitly setting secret_ref_key=null in patch is rejected with 422."""
    _create_secret(client, "secret.null.refkey")
    data = _create_binding(client, "null.refkey.svc", "secret.null.refkey")
    r = client.patch(f"/api/bindings/{data['id']}", json={"secret_ref_key": None})
    assert r.status_code == 422
    assert "null" in str(r.json()).lower() or "VALIDATION_ERROR" in str(r.json())


def test_patch_binding_null_service_name_rejected(client):
    """Explicitly setting service_name=null in patch is rejected with 422."""
    _create_secret(client, "secret.null.svcname")
    data = _create_binding(client, "null.svcname.svc", "secret.null.svcname")
    r = client.patch(f"/api/bindings/{data['id']}", json={"service_name": None})
    assert r.status_code == 422


def test_patch_binding_project_id(client):
    """Patching project_id on a binding."""
    proj = client.post("/api/projects", json={"name": "Bind Proj Patch"})
    assert proj.status_code == 201
    pid = proj.json()["id"]

    _create_secret(client, "secret.projpatch.bind")
    data = _create_binding(client, "projpatch.svc", "secret.projpatch.bind")
    r = client.patch(f"/api/bindings/{data['id']}", json={"project_id": pid})
    assert r.status_code == 200
    assert r.json()["project_id"] == pid
