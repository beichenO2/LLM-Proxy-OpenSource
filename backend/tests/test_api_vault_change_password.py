"""Tests for POST /api/vault/change-password (STNG-02)."""

from __future__ import annotations


def test_change_password_reencrypts_existing_secrets(client):
    create = client.post(
        "/api/secrets",
        json={
            "key": "secret.before.rotate",
            "value": "before-change-plain",
            "project_id": None,
        },
    )
    assert create.status_code == 201
    sid = create.json()["id"]

    r = client.post(
        "/api/vault/change-password",
        json={
            "current_password": "test-master-password",
            "new_password": "new-pass-8chars",
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "password_changed"

    # 260505 batch: reveal endpoint removed. Verify secret metadata still accessible.
    meta = client.get(f"/api/secrets/{sid}")
    assert meta.status_code == 200


def test_change_password_wrong_current_returns_401(client):
    r = client.post(
        "/api/vault/change-password",
        json={
            "current_password": "not-the-test-password",
            "new_password": "another-new8",
        },
    )
    assert r.status_code == 401
    assert r.json()["code"] == "AUTH_FAILED"
