"""FastAPI dependencies: database session and vault service."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.browser_session import COOKIE_NAME, validate_session
from app.services.vault import VaultService


def get_db() -> Generator[Session, None, None]:
    """Yield a sync SQLAlchemy session; commit on success, rollback on error, always close."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_vault(request: Request) -> VaultService:
    """Retrieve the process-wide VaultService instance from app state."""
    return request.app.state.vault


def _is_browser_request(request: Request) -> bool:
    origin = request.headers.get("origin")
    return bool(origin and origin.startswith("http"))


def _get_session_role(request: Request, db: Session) -> str | None:
    """Extract role from the browser session cookie. Returns None for non-browser or invalid."""
    if not _is_browser_request(request):
        return None
    token = request.cookies.get(COOKIE_NAME)
    row = validate_session(db, token)
    if row is None:
        raise HTTPException(
            status_code=401,
            detail={"detail": "Browser session expired — please unlock again", "code": "SESSION_EXPIRED"},
        )
    return row.role


def _require_session_cookie(request: Request, db: Session, *, require_full: bool = False) -> str:
    """Unconditionally require a valid session cookie."""
    token = request.cookies.get(COOKIE_NAME)
    row = validate_session(db, token)
    if row is None:
        raise HTTPException(
            status_code=401,
            detail={
                "detail": "Valid session required — unlock the vault via the GUI first",
                "code": "SESSION_REQUIRED",
            },
        )
    if require_full and row.role == "readonly":
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "Full session required — enter your master password to access sensitive data",
                "code": "FULL_SESSION_REQUIRED",
            },
        )
    return row.role


def require_unlocked_vault(
    request: Request,
    vault: Annotated[VaultService, Depends(get_vault)],
    db: Annotated[Session, Depends(get_db)],
) -> VaultService:
    """Vault must be unlocked. Validates browser session for browser requests."""
    if not vault.is_unlocked:
        raise HTTPException(
            status_code=423,
            detail={"detail": "Vault is locked", "code": "VAULT_LOCKED"},
        )
    if _is_browser_request(request):
        _get_session_role(request, db)
    return vault


def require_authenticated_session(
    request: Request,
    vault: Annotated[VaultService, Depends(get_vault)],
    db: Annotated[Session, Depends(get_db)],
) -> VaultService:
    """Vault unlocked + full session cookie (password-authenticated).

    No bearer tokens accepted — plaintext never leaves the vault boundary.
    """
    if not vault.is_unlocked:
        raise HTTPException(
            status_code=423,
            detail={"detail": "Vault is locked", "code": "VAULT_LOCKED"},
        )
    _require_session_cookie(request, db, require_full=True)
    return vault


def require_admin_vault(
    request: Request,
    vault: Annotated[VaultService, Depends(get_vault)],
    db: Annotated[Session, Depends(get_db)],
) -> VaultService:
    """Vault unlocked + admin-level auth (password session or admin vault role)."""
    vault = require_unlocked_vault(request, vault, db)
    if _is_browser_request(request):
        session_role = _get_session_role(request, db)
        if session_role != "admin":
            raise HTTPException(
                status_code=403,
                detail={"detail": "Admin privileges required", "code": "ADMIN_REQUIRED"},
            )
    elif vault.current_role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"detail": "Admin privileges required", "code": "ADMIN_REQUIRED"},
        )
    return vault
