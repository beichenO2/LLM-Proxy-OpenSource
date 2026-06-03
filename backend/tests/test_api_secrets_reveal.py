"""Tests for the plaintext-export ban: reveal/service-session/service-token must be unavailable.

260505 batch security overhaul: all plaintext export endpoints are permanently removed.
Plaintext can only leave PolarPrivate via:
  - /proxy/* (A-class bearer token reverse proxy)
  - /sign/{provider}/* (B-class HMAC signing service)
  - /api/d-class/grant (D-class controlled channel for third-party SDKs)

FastAPI returns 404 (not found) or 405 (method not allowed) depending on whether
the path prefix still exists; both indicate the endpoint is unreachable.
"""

from __future__ import annotations

REMOVED_STATUSES = {404, 405}


def test_reveal_endpoint_removed(client):
    """The reveal endpoint must not be reachable."""
    create = client.post(
        "/api/secrets",
        json={
            "key": "secret.reveal.test.removed",
            "value": "should-never-be-revealed",
            "project_id": None,
        },
    )
    assert create.status_code == 201
    sid = create.json()["id"]

    r = client.post(f"/api/secrets/{sid}/reveal")
    assert r.status_code in REMOVED_STATUSES, (
        f"reveal endpoint must be permanently removed, got {r.status_code}"
    )


def test_service_session_endpoint_removed(client):
    """The vault service-session endpoint must not be reachable."""
    r = client.post(
        "/api/vault/service-session",
        json={"service_name": "test"},
    )
    assert r.status_code in REMOVED_STATUSES, (
        f"service-session endpoint must be permanently removed, got {r.status_code}"
    )


def test_service_token_endpoint_removed(client):
    """The auth service-token endpoint must not be reachable."""
    r = client.post(
        "/api/auth/service-token",
        json={"name": "test"},
    )
    assert r.status_code in REMOVED_STATUSES, (
        f"service-token endpoint must be permanently removed, got {r.status_code}"
    )


def test_secret_metadata_endpoint_does_not_return_plaintext(client):
    """GET /api/secrets/{id} must never return plaintext value."""
    create = client.post(
        "/api/secrets",
        json={
            "key": "secret.metadata.test",
            "value": "plaintext-should-not-leak",
            "project_id": None,
        },
    )
    assert create.status_code == 201
    sid = create.json()["id"]

    r = client.get(f"/api/secrets/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert "value" not in body or body.get("value") != "plaintext-should-not-leak", (
        "GET /api/secrets/{id} must not leak plaintext"
    )
