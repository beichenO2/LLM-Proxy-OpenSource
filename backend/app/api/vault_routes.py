"""Vault unlock API (resolves vault state for the process)."""

from __future__ import annotations

import time
import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_vault, require_admin_vault, require_unlocked_vault
from app.db.models import DbMetadata
from app.logging_config import get_logger
from app.services.audit import append_audit_log
from app.services.browser_session import (
    COOKIE_MAX_AGE,
    COOKIE_NAME,
    create_session,
    revoke_all_sessions,
    revoke_session,
    validate_session,
)
from app.services.vault import VaultService, VaultUnlockError

router = APIRouter(prefix="/vault", tags=["vault"])
_LOG = get_logger(__name__)

_MAX_FAILURES = 10
_LOCKOUT_SECONDS = 60
_fail_lock = threading.Lock()
_fail_count = 0
_lockout_until = 0.0


def _set_session_cookie(
    response: Response,
    db: Session,
    *,
    role: str,
    username: str,
    user_id: str | None = None,
) -> None:
    """Create a persistent session and set the cookie."""
    token = create_session(db, role=role, username=username, user_id=user_id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.get("/status")
def vault_status(
    request: Request,
    vault: Annotated[VaultService, Depends(get_vault)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, bool | str | None]:
    """Return vault lock state, browser session validity, and session-specific role."""
    token = request.cookies.get(COOKIE_NAME)
    session_row = validate_session(db, token)
    has_valid_session = session_row is not None
    session_role = session_row.role if session_row else vault.current_role
    return {
        "locked": not vault.is_unlocked,
        "has_session": has_valid_session,
        "role": session_role,
    }


class VaultInitBody(BaseModel):
    master_password: SecretStr = Field(min_length=8)


class VaultUnlockBody(BaseModel):
    master_password: SecretStr = Field(min_length=1)
    username: str | None = None  # None or "admin" → admin unlock; otherwise user unlock


class ChangePasswordBody(BaseModel):
    current_password: SecretStr = Field(min_length=1)
    new_password: SecretStr = Field(min_length=8)


@router.post("/init")
def init_vault(
    body: VaultInitBody,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
    response: Response,
) -> dict[str, str]:
    """Initialize the vault with a master password (first-time setup only).

    Creates the DbMetadata row with salt, sentinel, and encrypted key material.
    Automatically unlocks the vault after creation.
    """
    meta = session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
    if meta is not None:
        raise HTTPException(
            status_code=409,
            detail={"detail": "vault already initialized", "code": "ALREADY_INIT"},
        )
    pw = body.master_password.get_secret_value()
    VaultService.create_new_database(session, pw)
    vault.unlock(session, pw)
    vault.enable_auto_unlock(session, pw)

    _set_session_cookie(response, session, role="admin", username="admin")

    append_audit_log(session, action="vault.init", detail=None, project_id=None)
    _LOG.info("vault_initialized")
    return {"status": "initialized_and_unlocked"}


@router.post("/unlock")
def unlock_vault(
    body: VaultUnlockBody,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
    response: Response,
) -> dict[str, str]:
    """Unlock the vault with the master password; sets a long-lived browser session cookie."""
    global _fail_count, _lockout_until

    with _fail_lock:
        if time.monotonic() < _lockout_until:
            remaining = int(_lockout_until - time.monotonic()) + 1
            _LOG.warning("vault_unlock_lockout", remaining_seconds=remaining)
            raise HTTPException(
                status_code=429,
                detail={
                    "detail": f"Too many failed attempts. Try again in {remaining}s.",
                    "code": "RATE_LIMITED",
                },
            )

    is_user_unlock = body.username and body.username.lower() != "admin"

    if not is_user_unlock:
        meta = session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
        if meta is None:
            raise HTTPException(
                status_code=412,
                detail={"detail": "vault not initialized — call POST /api/vault/init first", "code": "NOT_INITIALIZED"},
            )

        try:
            vault.unlock(session, body.master_password.get_secret_value())
        except VaultUnlockError:
            with _fail_lock:
                _fail_count += 1
                if _fail_count >= _MAX_FAILURES:
                    _lockout_until = time.monotonic() + _LOCKOUT_SECONDS
                    _LOG.warning("vault_unlock_lockout_triggered", fail_count=_fail_count)
            raise HTTPException(
                status_code=401,
                detail={"detail": "invalid master password", "code": "AUTH_FAILED"},
            ) from None

        vault.enable_auto_unlock(session, body.master_password.get_secret_value())

        from app.main import migrate_identity_encryption
        migrated = migrate_identity_encryption(session, vault)
        if migrated > 0:
            _LOG.info("identity_encryption_migrated_on_unlock", count=migrated)

        unlock_role = "admin"
        unlock_username = "admin"
        unlock_user_id = None
        audit_detail = None
    else:
        try:
            account = vault.unlock_as_user(session, body.username, body.master_password.get_secret_value())
        except VaultUnlockError as exc:
            err_msg = str(exc)
            with _fail_lock:
                _fail_count += 1
                if _fail_count >= _MAX_FAILURES:
                    _lockout_until = time.monotonic() + _LOCKOUT_SECONDS
            if "admin must unlock first" in err_msg:
                raise HTTPException(
                    status_code=412,
                    detail={"detail": err_msg, "code": "ADMIN_REQUIRED_FIRST"},
                ) from None
            raise HTTPException(
                status_code=401,
                detail={"detail": "invalid username or password", "code": "AUTH_FAILED"},
            ) from None
        unlock_role = "user"
        unlock_username = body.username  # type: ignore[assignment]
        unlock_user_id = account.id
        audit_detail = f"username={body.username}"

    with _fail_lock:
        _fail_count = 0
        _lockout_until = 0.0

    _set_session_cookie(
        response, session,
        role=unlock_role,
        username=unlock_username,
        user_id=unlock_user_id,
    )

    from app.main import migrate_identity_encryption
    migrate_identity_encryption(session, vault)

    append_audit_log(session, action="vault.unlock", detail=audit_detail, project_id=None)
    return {"status": "unlocked", "role": unlock_role}


_ALLOWED_AUTO_SESSION_ORIGINS = frozenset({
    "http://127.0.0.1:5170",
    "http://localhost:5170",
})


@router.post("/auto-session")
def auto_session(
    request: Request,
    vault: Annotated[VaultService, Depends(get_vault)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict[str, str]:
    """Grant a browser session without password when the vault is already unlocked.

    SECURITY: this endpoint is a privileged session factory. To prevent
    agents from obtaining cookies via ``curl -X POST``, it requires BOTH:
      1. A valid ``Origin`` header matching the frontend's known origins
      2. A ``Sec-Fetch-Site`` header (only set by real browsers)

    These headers cannot be spoofed by simple curl calls, and even if
    spoofed, the cookie has ``HttpOnly`` + ``SameSite=Lax`` so it cannot
    be exfiltrated by scripts on other origins.
    """
    origin = request.headers.get("origin", "")
    sec_fetch = request.headers.get("sec-fetch-site", "")

    if origin not in _ALLOWED_AUTO_SESSION_ORIGINS or not sec_fetch:
        _LOG.warning("auto_session_rejected", origin=origin, sec_fetch=sec_fetch)
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "Auto-session is only available from the PrivPortal GUI",
                "code": "BROWSER_REQUIRED",
            },
        )

    if not vault.is_unlocked:
        raise HTTPException(
            status_code=423,
            detail={"detail": "Vault is locked", "code": "VAULT_LOCKED"},
        )

    token = request.cookies.get(COOKIE_NAME)
    existing = validate_session(db, token)
    if existing is not None:
        return {"status": "already_has_session", "role": existing.role}

    _set_session_cookie(response, db, role="readonly", username="auto")
    _LOG.info("auto_session_granted", role="readonly")
    return {"status": "session_created", "role": "readonly"}


@router.post("/logout")
def logout(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict[str, str]:
    """Revoke only this browser's session. Vault stays unlocked for other sessions."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        revoke_session(db, token)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    _LOG.info("browser_session_logged_out")
    return {"status": "logged_out"}


@router.post("/lock")
def lock_vault(
    vault: Annotated[VaultService, Depends(require_admin_vault)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict[str, str]:
    """Admin-only: lock the vault globally, clearing all crypto keys and revoking all sessions."""
    vault.lock()
    revoke_all_sessions(db)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    _LOG.info("vault_locked_globally")
    return {"status": "locked"}


@router.post("/change-password")
def change_master_password_route(
    body: ChangePasswordBody,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_admin_vault)],
    response: Response,
) -> dict[str, str]:
    """Change the master password: re-derives keys, re-encrypts all secrets, resets sessions."""
    try:
        vault.change_master_password(
            session,
            body.current_password.get_secret_value(),
            body.new_password.get_secret_value(),
        )
    except VaultUnlockError:
        raise HTTPException(
            status_code=401,
            detail={"detail": "invalid current password", "code": "AUTH_FAILED"},
        ) from None

    new_pw = body.new_password.get_secret_value()
    vault.enable_auto_unlock(session, new_pw)

    revoke_all_sessions(session)
    _set_session_cookie(response, session, role="admin", username="admin")

    append_audit_log(session, action="vault.change_password", detail=None, project_id=None)
    return {"status": "password_changed"}
