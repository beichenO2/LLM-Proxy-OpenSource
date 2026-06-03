"""User account management API for multi-user key wrapping."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_vault, require_admin_vault
from app.db.models import UserAccount
from app.services.audit import append_audit_log
from app.services.vault import VaultService

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)


class UserRegister(BaseModel):
    """Self-registration body — same fields, different auth requirements."""
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserOut]
    total: int


@router.get("")
def list_users(
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_admin_vault)],
) -> UserListResponse:
    """List all registered user accounts (admin only)."""
    total = session.scalar(select(func.count()).select_from(UserAccount)) or 0
    rows = list(session.scalars(select(UserAccount)).all())
    return UserListResponse(
        items=[UserOut.model_validate(r) for r in rows],
        total=int(total),
    )


@router.post("", status_code=201)
def create_user(
    body: UserCreate,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_admin_vault)],
) -> UserOut:
    """Register a new user with key-wrapped vault access (admin only)."""
    if body.username.lower() == "admin":
        raise HTTPException(
            status_code=400,
            detail={"detail": "Cannot create user with reserved name 'admin'", "code": "RESERVED_USERNAME"},
        )

    existing = session.scalar(
        select(UserAccount).where(UserAccount.username == body.username)
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"detail": "Username already exists", "code": "DUPLICATE_USERNAME"},
        )

    account = vault.register_user(session, body.username, body.password)
    append_audit_log(session, action="user.create", detail=f"username={body.username}")
    return UserOut.model_validate(account)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: str,
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_admin_vault)],
) -> None:
    """Delete a user account (admin only)."""
    row = session.get(UserAccount, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    append_audit_log(session, action="user.delete", detail=f"username={row.username}")
    session.delete(row)


@router.post("/register", status_code=201)
def register_user(
    body: UserRegister,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(get_vault)],
) -> UserOut:
    """Self-service registration — vault must be admin-unlocked so fernet keys
    are available for wrapping, but caller does NOT need an admin session."""
    if not vault.is_unlocked or vault.current_role != "admin":
        raise HTTPException(
            status_code=412,
            detail={
                "detail": "Vault must be unlocked by admin before users can register",
                "code": "ADMIN_UNLOCK_REQUIRED",
            },
        )

    if body.username.lower() == "admin":
        raise HTTPException(
            status_code=400,
            detail={"detail": "Cannot register with reserved name 'admin'", "code": "RESERVED_USERNAME"},
        )

    existing = session.scalar(
        select(UserAccount).where(UserAccount.username == body.username)
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={"detail": "Username already exists", "code": "DUPLICATE_USERNAME"},
        )

    account = vault.register_user(session, body.username, body.password)
    append_audit_log(session, action="user.register", detail=f"username={body.username}")
    return UserOut.model_validate(account)
