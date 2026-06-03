"""Security tests: vault key storage and master password derivation."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DbMetadata
from app.services.vault import VaultService


def test_fernet_key_in_db_matches_derived_key(db_session: Session) -> None:
    """Verify that fernet_keys_json is encrypted at rest (schema v2) and the
    derived key can decrypt it to recover the same key material."""
    from cryptography.fernet import Fernet

    VaultService.create_new_database(db_session, "audit-test-pw-99")
    meta = db_session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
    assert meta is not None
    assert meta.schema_version >= 2, "schema v2+ encrypts fernet_keys_json"

    derived_key = VaultService._derive_fernet_key("audit-test-pw-99", meta.salt)
    fernet = Fernet(derived_key)
    decrypted_json = fernet.decrypt(meta.fernet_keys_json.encode("ascii")).decode("utf-8")
    stored_keys = json.loads(decrypted_json)
    assert len(stored_keys) == 1
    assert stored_keys[0] == derived_key.decode("ascii"), (
        "decrypted key must match derived key"
    )


def test_sentinel_validates_master_password(db_session: Session) -> None:
    """Sentinel ciphertext correctly rejects wrong passwords."""
    VaultService.create_new_database(db_session, "correct-pw")
    vault = VaultService()

    from app.services.vault import VaultUnlockError
    import pytest

    with pytest.raises(VaultUnlockError):
        vault.unlock(db_session, "wrong-pw")

    vault.unlock(db_session, "correct-pw")
    assert vault.is_unlocked


def test_master_password_registered_for_redaction(db_session: Session) -> None:
    """After unlock, the master password is in the redaction set."""
    from app.logging_config import _REDACTION_SUBSTRINGS, clear_registered_secrets

    clear_registered_secrets()
    VaultService.create_new_database(db_session, "redact-me-pw")
    vault = VaultService()
    vault.unlock(db_session, "redact-me-pw")

    assert "redact-me-pw" in _REDACTION_SUBSTRINGS
    clear_registered_secrets()


def test_encrypt_decrypt_roundtrip(db_session: Session) -> None:
    """Secret values survive encrypt → decrypt."""
    VaultService.create_new_database(db_session, "roundtrip-pw")
    vault = VaultService()
    vault.unlock(db_session, "roundtrip-pw")

    original = "sk-test-api-key-0123456789"
    ct = vault.encrypt_secret_value(original)
    assert ct != original
    assert vault.decrypt_secret_value(ct) == original
