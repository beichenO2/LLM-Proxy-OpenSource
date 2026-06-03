"""Extended vault tests — error paths, locked operations, change_password edge cases."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import DbMetadata
from app.services.vault import VaultService, VaultUnlockError


def test_unlock_without_metadata_raises(db_session):
    """Unlocking when no DbMetadata exists raises VaultUnlockError."""
    vault = VaultService()
    with pytest.raises(VaultUnlockError, match="not initialized"):
        vault.unlock(db_session, "any-password")


def test_encrypt_when_locked_raises(db_session):
    vault = VaultService()
    assert not vault.is_unlocked
    with pytest.raises(RuntimeError, match="locked"):
        vault.encrypt_secret_value("hello")


def test_decrypt_when_locked_raises(db_session):
    vault = VaultService()
    with pytest.raises(RuntimeError, match="locked"):
        vault.decrypt_secret_value("some-ciphertext")


def test_unlock_invalid_password_raises(db_session):
    VaultService.create_new_database(db_session, "correct-password")
    vault = VaultService()
    with pytest.raises(VaultUnlockError, match="invalid master password"):
        vault.unlock(db_session, "wrong-password")


def test_change_password_when_locked_raises(db_session):
    VaultService.create_new_database(db_session, "test-pw")
    vault = VaultService()
    with pytest.raises(RuntimeError, match="locked"):
        vault.change_master_password(db_session, "test-pw", "new-pw")


def test_unlock_invalid_fernet_keys_json(db_session):
    """If fernet_keys_json is corrupted, unlock raises VaultUnlockError."""
    VaultService.create_new_database(db_session, "test-pw")
    meta = db_session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
    meta.fernet_keys_json = "[]"
    db_session.commit()

    vault = VaultService()
    with pytest.raises(VaultUnlockError, match="corrupted encrypted key material"):
        vault.unlock(db_session, "test-pw")


def test_change_password_metadata_missing_raises(db_session):
    """change_master_password when DbMetadata is deleted raises."""
    VaultService.create_new_database(db_session, "test-pw")
    vault = VaultService()
    vault.unlock(db_session, "test-pw")

    meta = db_session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
    db_session.delete(meta)
    db_session.commit()

    with pytest.raises(VaultUnlockError, match="not initialized"):
        vault.change_master_password(db_session, "test-pw", "new-pw")
