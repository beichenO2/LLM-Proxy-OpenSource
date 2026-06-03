"""VaultService: sole production choke point for PBKDF2, Fernet, and MultiFernet (D-01–D-05)."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from base64 import urlsafe_b64encode

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DbMetadata, Secret, UserAccount
from app.logging_config import clear_registered_secrets, register_secrets_for_redaction

_KEYCHAIN_SERVICE = "PrivPortal"
_KEYCHAIN_ACCOUNT = "device-key"

PBKDF2_ITERATIONS = 480_000
PBKDF2_ALGORITHM = hashes.SHA256()
SALT_LENGTH_BYTES = 16
FERNET_KEY_LENGTH = 32

SENTINEL_PLAINTEXT = "PRIVPORTAL_V1_UNLOCK_SENTINEL"
AUTO_UNLOCK_MARKER = "PRIVPORTAL_AUTO_UNLOCK_V1"


class VaultUnlockError(ValueError):
    """Raised when the master password cannot decrypt the stored sentinel."""


class VaultService:
    """Derives Fernet keys from the master password; encrypts/decrypts secrets via MultiFernet.

    KDF: PBKDF2-HMAC-SHA256, ``480_000`` iterations (D-01).
    """


    __slots__ = ("_multi_fernet", "_unlocked", "_current_role", "_current_user_id", "_raw_fernet_keys", "_was_auto_unlocked")

    def __init__(self) -> None:
        self._multi_fernet: MultiFernet | None = None
        self._unlocked = False
        self._current_role: str | None = None  # "admin" | "user" | None
        self._current_user_id: str | None = None
        self._raw_fernet_keys: list[str] | None = None  # plaintext key strings for wrapping
        self._was_auto_unlocked = False

    @property
    def is_unlocked(self) -> bool:
        return self._unlocked

    @property
    def was_auto_unlocked(self) -> bool:
        """True if the vault was unlocked via device key (try_auto_unlock), not manual password."""
        return self._was_auto_unlocked

    @property
    def current_role(self) -> str | None:
        return self._current_role

    @property
    def current_user_id(self) -> str | None:
        return self._current_user_id

    def lock(self) -> None:
        """Discard in-memory key material and return to locked state."""
        self._multi_fernet = None
        self._unlocked = False
        self._current_role = None
        self._current_user_id = None
        self._raw_fernet_keys = None
        self._was_auto_unlocked = False

    @staticmethod
    def _derive_fernet_key(password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=PBKDF2_ALGORITHM,
            length=FERNET_KEY_LENGTH,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return urlsafe_b64encode(kdf.derive(password.encode("utf-8")))

    @staticmethod
    def create_new_database(session: Session, master_password: str) -> None:
        salt = os.urandom(SALT_LENGTH_BYTES)
        key = VaultService._derive_fernet_key(master_password, salt)
        fernet = Fernet(key)
        token = fernet.encrypt(SENTINEL_PLAINTEXT.encode("utf-8"))
        sentinel_ciphertext = token.decode("ascii")
        # v2 SECURITY: fernet_keys_json is now encrypted with the derived key itself.
        # An attacker with file-read access cannot recover secrets without the master password.
        keys_plaintext = json.dumps([key.decode("ascii")])
        encrypted_keys = fernet.encrypt(keys_plaintext.encode("utf-8")).decode("ascii")
        meta = DbMetadata(
            id=1,
            salt=salt,
            sentinel_ciphertext=sentinel_ciphertext,
            schema_version=2,
            fernet_keys_json=encrypted_keys,
        )
        session.merge(meta)
        session.commit()

    def unlock(self, session: Session, master_password: str) -> None:
        meta = session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
        if meta is None:
            import structlog
            _log = structlog.get_logger()
            _log.warning("vault_auto_migration", reason="metadata not initialized, auto-creating")
            self.create_new_database(session, master_password)
            meta = session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
            if meta is None:
                raise VaultUnlockError("database metadata auto-initialization failed")
        key = self._derive_fernet_key(master_password, meta.salt)
        fernet = Fernet(key)
        try:
            fernet.decrypt(meta.sentinel_ciphertext.encode("ascii"))
        except InvalidToken as exc:
            raise VaultUnlockError("invalid master password") from exc

        if meta.schema_version and meta.schema_version >= 2:
            try:
                decrypted_keys_json = fernet.decrypt(
                    meta.fernet_keys_json.encode("ascii")
                ).decode("utf-8")
            except InvalidToken as exc:
                raise VaultUnlockError("corrupted encrypted key material") from exc
            raw_keys = json.loads(decrypted_keys_json)
        else:
            raw_keys = json.loads(meta.fernet_keys_json or "[]")

        if not isinstance(raw_keys, list) or not raw_keys:
            raise VaultUnlockError("invalid fernet key configuration")
        self._multi_fernet = MultiFernet([Fernet(k) for k in raw_keys])
        self._raw_fernet_keys = raw_keys
        self._unlocked = True
        self._current_role = "admin"
        register_secrets_for_redaction([master_password])

    def encrypt_secret_value(self, plaintext: str) -> str:
        if not self._unlocked or self._multi_fernet is None:
            raise RuntimeError("vault is locked")
        return self._multi_fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt_secret_value(self, ciphertext: str) -> str:
        if not self._unlocked or self._multi_fernet is None:
            raise RuntimeError("vault is locked")
        return self._multi_fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")

    @staticmethod
    def _legacy_device_key_path() -> str:
        return os.path.join(os.path.expanduser("~"), ".privportal-device-key")

    @staticmethod
    def _keychain_read() -> bytes | None:
        """Read device key from macOS Keychain. Returns None if not found or not on macOS."""
        if platform.system() != "Darwin":
            return None
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", _KEYCHAIN_SERVICE, "-a", _KEYCHAIN_ACCOUNT, "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return None
            hex_key = result.stdout.strip()
            if not hex_key:
                return None
            return bytes.fromhex(hex_key)
        except Exception:
            return None

    @staticmethod
    def _keychain_write(raw_key: bytes) -> bool:
        """Store device key in macOS Keychain. Returns True on success."""
        if platform.system() != "Darwin":
            return False
        hex_key = raw_key.hex()
        try:
            subprocess.run(
                ["security", "add-generic-password",
                 "-s", _KEYCHAIN_SERVICE, "-a", _KEYCHAIN_ACCOUNT,
                 "-w", hex_key,
                 "-U",  # update if exists
                 "-j", "PrivPortal auto-unlock device key"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _keychain_delete() -> bool:
        """Remove device key from macOS Keychain."""
        if platform.system() != "Darwin":
            return False
        try:
            subprocess.run(
                ["security", "delete-generic-password", "-s", _KEYCHAIN_SERVICE, "-a", _KEYCHAIN_ACCOUNT],
                capture_output=True, text=True, timeout=5,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _migrate_file_key_to_keychain() -> bytes | None:
        """One-time migration: move device key from file to Keychain, delete the file."""
        path = VaultService._legacy_device_key_path()
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                raw = f.read()
            if len(raw) < 32:
                return None
            raw = raw[:32]
            if VaultService._keychain_write(raw):
                os.remove(path)
            return raw
        except Exception:
            return None

    @staticmethod
    def _get_or_create_device_key() -> bytes:
        """Return a 32-byte device-local key from macOS Keychain (preferred) or file (fallback).

        On macOS: stores key in Keychain, not on disk, so AI agents cannot read
        it via simple file operations. On first run, migrates any existing file
        key to Keychain and deletes the file.

        On non-macOS: falls back to a 0600-permission file in $HOME.
        """
        if platform.system() == "Darwin":
            existing = VaultService._keychain_read()
            if existing is not None and len(existing) >= 32:
                return urlsafe_b64encode(existing[:32])

            migrated = VaultService._migrate_file_key_to_keychain()
            if migrated is not None:
                return urlsafe_b64encode(migrated)

            raw = os.urandom(32)
            VaultService._keychain_write(raw)
            return urlsafe_b64encode(raw)

        path = VaultService._legacy_device_key_path()
        if os.path.exists(path):
            with open(path, "rb") as f:
                key = f.read()
            if len(key) >= 32:
                return urlsafe_b64encode(key[:32])
        raw = os.urandom(32)
        with open(path, "wb") as f:
            f.write(raw)
        os.chmod(path, 0o600)
        return urlsafe_b64encode(raw)

    def enable_auto_unlock(self, session: Session, master_password: str) -> None:
        """Encrypt the master password with a device-local key and store in DB."""
        device_key = self._get_or_create_device_key()
        f = Fernet(device_key)
        encrypted_pw = f.encrypt(master_password.encode("utf-8")).decode("ascii")
        meta = session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
        if meta is not None:
            meta.auto_unlock_token = encrypted_pw
            session.flush()

    def try_auto_unlock(self, session: Session) -> bool:
        """Decrypt the stored password using device-local key, then unlock. Returns True on success.

        Sets ``_was_auto_unlocked`` so that service-session can verify the unlock
        was via the macOS Keychain device key (security equivalent to user login).
        """
        meta = session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
        if meta is None or not meta.auto_unlock_token:
            return False
        try:
            device_key = self._get_or_create_device_key()
            f = Fernet(device_key)
            pw = f.decrypt(meta.auto_unlock_token.encode("ascii")).decode("utf-8")
            self.unlock(session, pw)
            self._was_auto_unlocked = True
            return True
        except Exception:
            return False

    def change_master_password(self, session: Session, current_password: str, new_password: str) -> None:
        """Rotate KDF salt and Fernet keys: verify *current_password*, re-encrypt all secrets.

        Uses the same flow as :meth:`create_new_database` for new key material (random salt,
        PBKDF2-derived Fernet key, sentinel ciphertext, single-key ``fernet_keys_json``) while
        preserving existing secret plaintext by decrypting with the current MultiFernet and
        encrypting with the new key. Caller must have unlocked the vault so ciphertext can be read.
        """
        if not self._unlocked or self._multi_fernet is None:
            raise RuntimeError("vault is locked")

        meta = session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
        if meta is None:
            raise VaultUnlockError("database metadata not initialized")

        key_current = self._derive_fernet_key(current_password, meta.salt)
        f_current = Fernet(key_current)
        try:
            f_current.decrypt(meta.sentinel_ciphertext.encode("ascii"))
        except InvalidToken as exc:
            raise VaultUnlockError("invalid current password") from exc

        rows = list(session.scalars(select(Secret)).all())
        plaintext_by_id: dict[str, str] = {
            r.id: self.decrypt_secret_value(r.value) for r in rows
        }

        new_salt = os.urandom(SALT_LENGTH_BYTES)
        new_key = self._derive_fernet_key(new_password, new_salt)
        new_fernet = Fernet(new_key)
        new_sentinel = new_fernet.encrypt(SENTINEL_PLAINTEXT.encode("utf-8")).decode("ascii")
        keys_plaintext = json.dumps([new_key.decode("ascii")])
        encrypted_keys = new_fernet.encrypt(keys_plaintext.encode("utf-8")).decode("ascii")

        meta.salt = new_salt
        meta.sentinel_ciphertext = new_sentinel
        meta.fernet_keys_json = encrypted_keys
        meta.schema_version = 2
        session.merge(meta)

        new_multi = MultiFernet([new_fernet])

        for sid, plaintext in plaintext_by_id.items():
            row = session.get(Secret, sid)
            if row is not None:
                row.value = new_multi.encrypt(plaintext.encode("utf-8")).decode("ascii")

        # Only swap in-memory state after all DB mutations succeed (flush validates
        # the session; if commit later fails the caller rolls back the session, and
        # the next unlock will re-derive keys from the DB state).
        session.flush()
        self._multi_fernet = new_multi
        new_raw_keys = [new_key.decode("ascii")]
        self._raw_fernet_keys = new_raw_keys

        # Re-wrap fernet keys for all user accounts with the new key material
        self._rewrap_all_user_keys(session, new_raw_keys)

        clear_registered_secrets()
        register_secrets_for_redaction([new_password])

    # ------------------------------------------------------------------
    # Multi-user key wrapping
    # ------------------------------------------------------------------

    def register_user(self, session: Session, username: str, password: str) -> UserAccount:
        """Create a new user account with key-wrapped access to the vault.

        The admin's fernet_keys are wrapped (Fernet-encrypted) with a key derived
        from the user's password. The user can later unwrap them to build a read-only
        MultiFernet for proxy access.
        """
        if not self._unlocked or self._current_role != "admin":
            raise RuntimeError("vault must be unlocked as admin to register users")
        if self._raw_fernet_keys is None:
            raise RuntimeError("no fernet keys available for wrapping")

        from uuid import uuid4

        user_salt = os.urandom(SALT_LENGTH_BYTES)
        user_key = self._derive_fernet_key(password, user_salt)
        user_fernet = Fernet(user_key)

        user_sentinel = user_fernet.encrypt(SENTINEL_PLAINTEXT.encode("utf-8")).decode("ascii")

        keys_json = json.dumps(self._raw_fernet_keys)
        wrapped = user_fernet.encrypt(keys_json.encode("utf-8")).decode("ascii")

        account = UserAccount(
            id=str(uuid4()),
            username=username,
            salt=user_salt,
            sentinel_ciphertext=user_sentinel,
            wrapped_fernet_keys=wrapped,
            role="user",
        )
        session.add(account)
        session.flush()
        return account

    def verify_user_password(self, session: Session, username: str, password: str) -> UserAccount:
        """Verify a non-admin user's password without mutating vault state.

        Returns the UserAccount on success. Raises VaultUnlockError on failure.
        Use this when the vault is already unlocked and a user just needs a session.
        """
        account = session.scalar(
            select(UserAccount).where(UserAccount.username == username)
        )
        if account is None:
            raise VaultUnlockError("user not found")

        user_key = self._derive_fernet_key(password, account.salt)
        user_fernet = Fernet(user_key)

        try:
            user_fernet.decrypt(account.sentinel_ciphertext.encode("ascii"))
        except InvalidToken as exc:
            raise VaultUnlockError("invalid user password") from exc

        if not account.wrapped_fernet_keys:
            if self._unlocked and self._raw_fernet_keys:
                keys_json = json.dumps(self._raw_fernet_keys)
                account.wrapped_fernet_keys = user_fernet.encrypt(
                    keys_json.encode("utf-8")
                ).decode("ascii")
                session.flush()
            else:
                raise VaultUnlockError(
                    "wrapped keys not initialized — admin must unlock first on this device"
                )
        return account

    def unlock_as_user(self, session: Session, username: str, password: str) -> UserAccount:
        """Unlock the vault as a non-admin user via key unwrapping.

        If the vault is already unlocked, only verifies the password without
        overwriting the global crypto state or admin role. Returns the UserAccount.
        """
        account = self.verify_user_password(session, username, password)

        if self._unlocked:
            return account

        user_key = self._derive_fernet_key(password, account.salt)
        user_fernet = Fernet(user_key)

        try:
            decrypted = user_fernet.decrypt(
                account.wrapped_fernet_keys.encode("ascii")
            ).decode("utf-8")
        except InvalidToken as exc:
            raise VaultUnlockError("cannot unwrap fernet keys") from exc

        raw_keys = json.loads(decrypted)
        if not isinstance(raw_keys, list) or not raw_keys:
            raise VaultUnlockError("invalid unwrapped key material")

        self._multi_fernet = MultiFernet([Fernet(k) for k in raw_keys])
        self._raw_fernet_keys = raw_keys
        self._unlocked = True
        self._current_role = "user"
        self._current_user_id = account.id
        return account

    def _rewrap_all_user_keys(self, session: Session, new_raw_keys: list[str]) -> None:
        """Re-wrap fernet keys for all user accounts after admin password change."""
        accounts = list(session.scalars(select(UserAccount)).all())
        keys_json = json.dumps(new_raw_keys)
        for account in accounts:
            if not account.wrapped_fernet_keys:
                continue
            # We can't re-derive the user's key (no password), so we set
            # wrapped_fernet_keys to null — user must re-authenticate once
            # after admin password change to re-wrap with their key.
            account.wrapped_fernet_keys = None
        session.flush()
