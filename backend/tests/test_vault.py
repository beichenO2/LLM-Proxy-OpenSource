"""Tests for VaultService (SECU-01, SECU-02, SCRT-02)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DbMetadata
from app.logging_config import clear_registered_secrets
from app.services.vault import VaultService, VaultUnlockError


@pytest.fixture(autouse=True)
def _isolate_redaction_registry() -> None:
    clear_registered_secrets()
    yield
    clear_registered_secrets()


def test_master_password_unlock(db_session: Session) -> None:
    VaultService.create_new_database(db_session, "test-password-123")
    vault = VaultService()
    with pytest.raises(VaultUnlockError):
        vault.unlock(db_session, "wrong-password")
    vault.unlock(db_session, "test-password-123")
    ciphertext = vault.encrypt_secret_value("secret-payload-xyz")
    assert vault.decrypt_secret_value(ciphertext) == "secret-payload-xyz"


def test_kdf_pbkdf2(db_session: Session) -> None:
    VaultService.create_new_database(db_session, "test-password-123")
    meta = db_session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
    assert meta is not None
    assert len(meta.salt) == 16


def test_encrypt_decrypt_fernet(db_session: Session) -> None:
    VaultService.create_new_database(db_session, "test-password-123")
    vault = VaultService()
    vault.unlock(db_session, "test-password-123")
    plaintext = "secret-payload-xyz"
    ciphertext = vault.encrypt_secret_value(plaintext)
    assert ciphertext != plaintext
    assert vault.decrypt_secret_value(ciphertext) == plaintext
    assert ciphertext.startswith("gAAAAA")


def test_lock_discards_key_material(db_session: Session) -> None:
    """After lock(), encrypt/decrypt raise RuntimeError."""
    VaultService.create_new_database(db_session, "test-password-123")
    vault = VaultService()
    vault.unlock(db_session, "test-password-123")
    assert vault.is_unlocked is True

    vault.lock()
    assert vault.is_unlocked is False

    with pytest.raises(RuntimeError, match="vault is locked"):
        vault.encrypt_secret_value("anything")
    with pytest.raises(RuntimeError, match="vault is locked"):
        vault.decrypt_secret_value("anything")


def test_lock_then_re_unlock(db_session: Session) -> None:
    """Vault can be re-unlocked after lock()."""
    VaultService.create_new_database(db_session, "test-password-123")
    vault = VaultService()
    vault.unlock(db_session, "test-password-123")
    ct = vault.encrypt_secret_value("hello")
    vault.lock()
    vault.unlock(db_session, "test-password-123")
    assert vault.decrypt_secret_value(ct) == "hello"


def test_encrypt_raises_when_locked() -> None:
    """A freshly constructed VaultService rejects encrypt/decrypt."""
    vault = VaultService()
    with pytest.raises(RuntimeError, match="vault is locked"):
        vault.encrypt_secret_value("x")
    with pytest.raises(RuntimeError, match="vault is locked"):
        vault.decrypt_secret_value("x")
