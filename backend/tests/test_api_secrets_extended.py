"""Extended secrets API tests — edge cases, validation, CRUD completeness."""

from __future__ import annotations

import httpx


def _create_secret(client, key: str, value: str = "test-val", **kw) -> dict:
    r = client.post(
        "/api/secrets",
        json={"key": key, "value": value, "project_id": None, **kw},
    )
    assert r.status_code == 201
    return r.json()


def test_create_secret_invalid_key_no_dot(client):
    """Key without dot notation is rejected with 422."""
    r = client.post(
        "/api/secrets",
        json={"key": "nodotkey", "value": "x", "project_id": None},
    )
    assert r.status_code == 422


def test_create_secret_duplicate_key_rejected(client):
    _create_secret(client, "secret.dup.test")
    r = client.post(
        "/api/secrets",
        json={"key": "secret.dup.test", "value": "y", "project_id": None},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "DUPLICATE_KEY"


def test_get_single_secret(client):
    data = _create_secret(client, "secret.get.single")
    sid = data["id"]
    r = client.get(f"/api/secrets/{sid}")
    assert r.status_code == 200
    assert r.json()["key"] == "secret.get.single"
    assert "value" not in r.json()


def test_get_secret_not_found(client):
    r = client.get("/api/secrets/nonexistent-id")
    assert r.status_code == 404
    assert r.json()["code"] == "ENTITY_NOT_FOUND"


def test_patch_secret_value_reencrypts(client):
    """Patching value re-encrypts. Plaintext check removed in 260505 batch
    (reveal endpoint deleted); we now assert metadata is intact."""
    data = _create_secret(client, "secret.patch.val", value="original")
    sid = data["id"]

    r = client.patch(f"/api/secrets/{sid}", json={"value": "updated-secret"})
    assert r.status_code == 200

    meta = client.get(f"/api/secrets/{sid}")
    assert meta.status_code == 200
    assert meta.json().get("key") == "secret.patch.val"


def test_patch_secret_key_with_duplicate_rejected(client):
    _create_secret(client, "secret.patchdup.a")
    data_b = _create_secret(client, "secret.patchdup.b")
    r = client.patch(f"/api/secrets/{data_b['id']}", json={"key": "secret.patchdup.a"})
    assert r.status_code == 409
    assert r.json()["code"] == "DUPLICATE_KEY"


def test_patch_secret_not_found(client):
    r = client.patch("/api/secrets/nonexistent-id", json={"enabled": False})
    assert r.status_code == 404


def test_patch_secret_base_url_and_category(client):
    data = _create_secret(client, "secret.patch.meta")
    sid = data["id"]
    r = client.patch(f"/api/secrets/{sid}", json={"base_url": "https://new.api.com", "category": "openai"})
    assert r.status_code == 200
    assert r.json()["base_url"] == "https://new.api.com"
    assert r.json()["category"] == "openai"


def test_rotate_secret_not_found(client):
    r = client.post("/api/secrets/nonexistent-id/rotate", json={"value": "new"})
    assert r.status_code == 404


def test_list_secrets_filter_by_q(client):
    _create_secret(client, "secret.filter.alpha")
    _create_secret(client, "secret.filter.beta")
    r = client.get("/api/secrets?q=alpha")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all("alpha" in x["key"] for x in items)


def test_list_secrets_filter_by_category(client):
    _create_secret(client, "secret.cat.one", category="openai")
    _create_secret(client, "secret.cat.two", category="dashscope")
    r = client.get("/api/secrets?category=openai")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(x["category"] == "openai" for x in items)


def test_list_secrets_pagination(client):
    for i in range(5):
        _create_secret(client, f"secret.page.{i}")
    r = client.get("/api/secrets?offset=0&limit=2")
    assert r.status_code == 200
    assert len(r.json()["items"]) <= 2
    assert r.json()["total"] >= 5


def test_connectivity_404_fallback_to_get(client, monkeypatch):
    """When HEAD returns 404, connectivity test falls back to GET."""
    data = _create_secret(client, "secret.conn.fallback", base_url="https://api.example.com")
    sid = data["id"]

    class _Resp404:
        status_code = 404

    class _Resp200:
        status_code = 200

    call_log = []

    async def fake_head(self, url, **kw):
        call_log.append("head")
        return _Resp404()

    async def fake_get(self, url, **kw):
        call_log.append("get")
        return _Resp200()

    class _FakeClient:
        head = fake_head
        get = fake_get

    class _CM:
        async def __aenter__(self):
            return _FakeClient()

        async def __aexit__(self, *_a):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", lambda *_a, **_k: _CM())

    r = client.post(f"/api/secrets/{sid}/test-connectivity")
    assert r.status_code == 200
    assert "head" in call_log
    assert "get" in call_log
    assert r.json()["reachable"] is True


def test_connectivity_request_error(client, monkeypatch):
    """httpx.RequestError during connectivity returns reachable=false."""
    data = _create_secret(client, "secret.conn.err", base_url="https://bad.host.example.com")
    sid = data["id"]

    async def raise_err(self, url, **kw):
        raise httpx.ConnectError("DNS failure")

    class _FakeClient:
        head = raise_err
        get = raise_err

    class _CM:
        async def __aenter__(self):
            return _FakeClient()

        async def __aexit__(self, *_a):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", lambda *_a, **_k: _CM())

    r = client.post(f"/api/secrets/{sid}/test-connectivity")
    assert r.status_code == 200
    data = r.json()
    assert data["reachable"] is False
    assert data["error"] is not None


def test_connectivity_not_found(client):
    r = client.post("/api/secrets/nonexistent-id/test-connectivity")
    assert r.status_code == 404


def test_patch_secret_key_and_project_id(client):
    """Patching key and project_id together triggers uniqueness check."""
    proj = client.post("/api/projects", json={"name": "Secret Proj"})
    assert proj.status_code == 201
    pid = proj.json()["id"]

    data = _create_secret(client, "secret.movable.key", value="v")
    sid = data["id"]
    r = client.patch(f"/api/secrets/{sid}", json={"key": "secret.moved.key", "project_id": pid})
    assert r.status_code == 200
    assert r.json()["key"] == "secret.moved.key"
    assert r.json()["project_id"] == pid


def test_list_secrets_filter_by_project_id(client):
    """Filter by project_id returns only matching secrets."""
    proj = client.post("/api/projects", json={"name": "Secret Proj Filter"})
    assert proj.status_code == 201
    pid = proj.json()["id"]

    client.post(
        "/api/secrets",
        json={"key": "secret.projfilter.one", "value": "v", "project_id": pid},
    )
    r = client.get(f"/api/secrets?project_id={pid}")
    assert r.status_code == 200
    items = r.json()["items"]
    assert all(x["project_id"] == pid for x in items)


def test_list_secrets_no_filters_returns_all(client):
    """List without filters returns total count."""
    _create_secret(client, "secret.nofilter.x")
    r = client.get("/api/secrets")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_delete_secret(client):
    """DELETE /api/secrets/{id} removes the secret and returns 204."""
    data = _create_secret(client, "secret.del.target")
    sid = data["id"]
    r = client.delete(f"/api/secrets/{sid}")
    assert r.status_code == 204

    r = client.get(f"/api/secrets/{sid}")
    assert r.status_code == 404


def test_delete_secret_not_found(client):
    """DELETE on a nonexistent id returns 404."""
    r = client.delete("/api/secrets/nonexistent-id")
    assert r.status_code == 404
    assert r.json()["code"] == "ENTITY_NOT_FOUND"


def test_delete_secret_idempotent_second_call_404(client):
    """Deleting an already-deleted secret returns 404."""
    data = _create_secret(client, "secret.del.twice")
    sid = data["id"]
    r1 = client.delete(f"/api/secrets/{sid}")
    assert r1.status_code == 204
    r2 = client.delete(f"/api/secrets/{sid}")
    assert r2.status_code == 404


def test_patch_secret_explicit_null_key_rejected(client):
    """Explicitly setting key=null in PATCH body is rejected with 422."""
    data = _create_secret(client, "secret.nullkey.test")
    r = client.patch(f"/api/secrets/{data['id']}", json={"key": None})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_patch_secret_explicit_null_value_rejected(client):
    """Explicitly setting value=null in PATCH body is rejected with 422."""
    data = _create_secret(client, "secret.nullval.test")
    r = client.patch(f"/api/secrets/{data['id']}", json={"value": None})
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


def test_patch_secret_value_vault_locked(client, app, db_session):
    """Patching value when vault is locked returns 423."""
    data = _create_secret(client, "secret.locked.patch")
    sid = data["id"]

    app.state.vault.lock()
    try:
        r = client.patch(f"/api/secrets/{sid}", json={"value": "new-val"})
        assert r.status_code == 423
        assert r.json()["code"] == "VAULT_LOCKED"
    finally:
        app.state.vault.unlock(db_session, "test-master-password")
