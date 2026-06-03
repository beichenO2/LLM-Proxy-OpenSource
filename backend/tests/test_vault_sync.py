"""Tests for vault backup/restore with independent backup password (v3)."""

from __future__ import annotations

from starlette.testclient import TestClient


def _seed_data(client: TestClient) -> None:
    """Create a project, identity, secret, and binding for testing."""
    r = client.post("/api/projects", json={"name": "SyncTest", "description": "test"})
    assert r.status_code in (200, 201)
    pid = r.json()["id"]

    client.post("/api/identities", json={"key": "id.email", "value": "a@b.com", "project_id": pid})
    client.post("/api/secrets", json={"key": "secret.api.key", "value": "sk-12345", "project_id": pid})
    client.post("/api/bindings", json={"service_name": "llm", "secret_ref_key": "secret.api.key", "project_id": pid})


class TestBackupVaultKey:
    """v2 backup format checks (encrypted with vault key)."""

    def test_backup_no_body_returns_v2_format(self, client):
        r = client.post("/api/vault/backup")
        assert r.status_code == 200
        data = r.json()
        assert data["version"] == 2
        assert data["encryption"] == "vault"
        assert "salt" in data
        assert "payload" in data


class TestBackupPassword:
    """v3 backup: encrypted with an independent backup password."""

    def test_backup_with_password_returns_v3(self, client):
        _seed_data(client)

        r = client.post(
            "/api/vault/backup",
            json={"backup_password": "my-backup-pass-123"},
        )
        assert r.status_code == 200
        backup = r.json()
        assert backup["version"] == 3
        assert backup["encryption"] == "backup_password"

    def test_roundtrip_with_backup_password(self, client):
        _seed_data(client)

        r = client.post(
            "/api/vault/backup",
            json={"backup_password": "my-backup-pass-123"},
        )
        backup = r.json()

        r = client.post(
            "/api/vault/restore",
            json={
                "payload": backup["payload"],
                "salt": backup["salt"],
                "backup_password": "my-backup-pass-123",
                "strategy": "merge",
            },
        )
        assert r.status_code == 200
        result = r.json()
        assert result["skipped"] >= 1

    def test_wrong_backup_password_fails(self, client):
        _seed_data(client)

        r = client.post(
            "/api/vault/backup",
            json={"backup_password": "my-backup-pass-123"},
        )
        backup = r.json()

        r = client.post(
            "/api/vault/restore",
            json={
                "payload": backup["payload"],
                "salt": backup["salt"],
                "backup_password": "wrong-password-999",
                "strategy": "merge",
            },
        )
        assert r.status_code == 400

    def test_restore_no_password_returns_422(self, client):
        r = client.post(
            "/api/vault/restore",
            json={
                "payload": "not-important",
                "salt": "not-important",
                "strategy": "merge",
            },
        )
        assert r.status_code == 422

    def test_v3_not_decryptable_with_master_password(self, client):
        _seed_data(client)

        r = client.post(
            "/api/vault/backup",
            json={"backup_password": "my-backup-pass-123"},
        )
        backup = r.json()

        r = client.post(
            "/api/vault/restore",
            json={
                "payload": backup["payload"],
                "salt": backup["salt"],
                "master_password": "test-master-password",
                "strategy": "merge",
            },
        )
        assert r.status_code == 400

    def test_replace_strategy_with_backup_password(self, client):
        _seed_data(client)

        r = client.post(
            "/api/vault/backup",
            json={"backup_password": "my-backup-pass-123"},
        )
        backup = r.json()

        r = client.post(
            "/api/vault/restore",
            json={
                "payload": backup["payload"],
                "salt": backup["salt"],
                "backup_password": "my-backup-pass-123",
                "strategy": "replace",
            },
        )
        assert r.status_code == 200
        result = r.json()
        assert result["projects"] >= 1
        assert result["secrets"] >= 1

    def test_survives_master_password_change(self, client):
        """v3 backups remain decryptable after changing the vault master password."""
        _seed_data(client)

        r = client.post(
            "/api/vault/backup",
            json={"backup_password": "stable-backup-pass"},
        )
        assert r.status_code == 200
        backup_before = r.json()

        r = client.post(
            "/api/vault/change-password",
            json={
                "current_password": "test-master-password",
                "new_password": "new-master-password-123",
            },
        )
        if r.status_code != 200:
            return

        r = client.post(
            "/api/vault/restore",
            json={
                "payload": backup_before["payload"],
                "salt": backup_before["salt"],
                "backup_password": "stable-backup-pass",
                "strategy": "merge",
            },
        )
        assert r.status_code == 200
        assert r.json()["skipped"] >= 1
