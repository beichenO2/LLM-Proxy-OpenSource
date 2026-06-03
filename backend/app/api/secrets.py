"""Secret entries API (SCRT-01, D-22–D-25)."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_vault, require_admin_vault, require_unlocked_vault
from app.api.exceptions import raise_duplicate, raise_not_found
from app.db.models import Secret
from app.services.audit import append_audit_log
from app.services.vault import VaultService

router = APIRouter(prefix="/secrets", tags=["secrets"])


def _dot_notation_key(v: str) -> str:
    if "." not in v:
        raise ValueError("key must use hierarchical dot notation (must contain '.')")
    return v


class SecretCreate(BaseModel):
    key: str = Field(min_length=1, max_length=512)
    value: str = Field(min_length=1)
    project_id: str | None = None
    enabled: bool = True
    base_url: str | None = None
    category: str | None = None

    @field_validator("key")
    @classmethod
    def key_dot_notation(cls, v: str) -> str:
        return _dot_notation_key(v)


class SecretUpdate(BaseModel):
    key: str | None = Field(default=None, min_length=1, max_length=512)
    value: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    base_url: str | None = None
    category: str | None = None
    project_id: str | None = None

    @field_validator("key")
    @classmethod
    def key_dot_notation(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _dot_notation_key(v)


class SecretOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    enabled: bool
    project_id: str | None
    base_url: str | None
    category: str | None
    rotated_at: datetime | None
    created_at: datetime
    updated_at: datetime
    has_value: bool = True  # True if secret has a non-empty value


class SecretListResponse(BaseModel):
    items: list[SecretOut]
    total: int


class RotateBody(BaseModel):
    value: str = Field(min_length=1)


class ConnectivityResult(BaseModel):
    reachable: bool
    status_code: int | None
    latency_ms: float
    error: str | None = None


def _assert_unique_secret_key(
    session: Session,
    project_id: str | None,
    key: str,
    exclude_id: str | None,
) -> None:
    stmt = select(Secret).where(Secret.key == key)
    if project_id is None:
        stmt = stmt.where(Secret.project_id.is_(None))
    else:
        stmt = stmt.where(Secret.project_id == project_id)
    if exclude_id is not None:
        stmt = stmt.where(Secret.id != exclude_id)
    if session.scalar(stmt) is not None:
        raise_duplicate("secret key")


def _secret_to_out(row: Secret) -> SecretOut:
    """Convert Secret model to SecretOut with has_value computed."""
    return SecretOut(
        id=row.id,
        key=row.key,
        enabled=row.enabled,
        project_id=row.project_id,
        base_url=row.base_url,
        category=row.category,
        rotated_at=row.rotated_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        has_value=bool(row.value and row.value.strip()),
    )


@router.get("")
def list_secrets(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=0, le=200),
    q: str | None = None,
    category: str | None = None,
    project_id: str | None = None,
) -> SecretListResponse:
    """Return paginated secret metadata (without ciphertext values)."""
    conditions = []
    if vault.current_role != "admin":
        conditions.append(Secret.owner_id == vault.current_user_id)
    if q is not None and q != "":
        conditions.append(Secret.key.contains(q))
    if category is not None:
        conditions.append(Secret.category == category)
    if project_id is not None:
        conditions.append(Secret.project_id == project_id)
    count_stmt = select(func.count()).select_from(Secret)
    list_stmt = select(Secret)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
        list_stmt = list_stmt.where(*conditions)
    total = session.scalar(count_stmt) or 0
    rows = session.scalars(list_stmt.offset(offset).limit(limit)).all()
    return SecretListResponse(
        items=[_secret_to_out(r) for r in rows],
        total=int(total),
    )


@router.post("", status_code=201)
def create_secret(
    body: SecretCreate,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> SecretOut:
    """Create a new secret; plaintext value is Fernet-encrypted before storage."""
    _assert_unique_secret_key(session, body.project_id, body.key, None)
    sid = str(uuid.uuid4())
    ciphertext = vault.encrypt_secret_value(body.value)
    row = Secret(
        id=sid,
        project_id=body.project_id,
        key=body.key,
        value=ciphertext,
        enabled=body.enabled,
        base_url=body.base_url,
        category=body.category,
        rotated_at=None,
        owner_id=vault.current_user_id,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    append_audit_log(session, action="secret.create", detail=f"key={row.key}", project_id=row.project_id)
    return _secret_to_out(row)


@router.get("/{secret_id}")
def get_secret(
    secret_id: str,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> SecretOut:
    """Return metadata for a single secret (without ciphertext)."""
    row = session.get(Secret, secret_id)
    if row is None:
        raise_not_found("Secret")
    if vault.current_role != "admin" and row.owner_id != vault.current_user_id:
        raise_not_found("Secret")
    return _secret_to_out(row)


@router.patch("/{secret_id}")
def patch_secret(
    secret_id: str,
    body: SecretUpdate,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> SecretOut:
    """Partial update of a secret. Re-encrypts if a new value is provided."""
    row = session.get(Secret, secret_id)
    if row is None:
        raise_not_found("Secret")
    if vault.current_role != "admin" and row.owner_id != vault.current_user_id:
        raise HTTPException(status_code=403, detail="Cannot edit another user's entry")
    data = body.model_dump(exclude_unset=True)
    if "key" in data and data["key"] is None:
        raise HTTPException(
            status_code=422,
            detail={"detail": "key cannot be null", "code": "VALIDATION_ERROR"},
        )
    if "value" in data and data["value"] is None:
        raise HTTPException(
            status_code=422,
            detail={"detail": "value cannot be null", "code": "VALIDATION_ERROR"},
        )
    if "value" in data:
        if not vault.is_unlocked:
            raise HTTPException(
                status_code=423,
                detail={"detail": "Vault is locked", "code": "VAULT_LOCKED"},
            )
        row.value = vault.encrypt_secret_value(data["value"])
    if "key" in data or "project_id" in data:
        new_key = data["key"] if "key" in data else row.key
        new_pid = data["project_id"] if "project_id" in data else row.project_id
        _assert_unique_secret_key(session, new_pid, new_key, secret_id)
    if "key" in data:
        row.key = data["key"]
    if "project_id" in data:
        row.project_id = data["project_id"]
    if "enabled" in data:
        row.enabled = data["enabled"]
    if "base_url" in data:
        row.base_url = data["base_url"]
    if "category" in data:
        row.category = data["category"]
    session.flush()
    session.refresh(row)
    return _secret_to_out(row)


@router.post("/{secret_id}/rotate")
def rotate_secret(
    secret_id: str,
    body: RotateBody,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> SecretOut:
    """Replace secret value with a new plaintext and update ``rotated_at``."""
    row = session.get(Secret, secret_id)
    if row is None:
        raise_not_found("Secret")
    if vault.current_role != "admin" and row.owner_id != vault.current_user_id:
        raise HTTPException(status_code=403, detail="Cannot rotate another user's entry")
    row.value = vault.encrypt_secret_value(body.value)
    row.rotated_at = datetime.now(timezone.utc)
    session.flush()
    session.refresh(row)
    append_audit_log(session, action="secret.rotate", detail=f"key={row.key}", project_id=row.project_id)
    return _secret_to_out(row)


@router.delete("/{secret_id}", status_code=204)
def delete_secret(
    secret_id: str,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> None:
    """Delete a secret by ID."""
    row = session.get(Secret, secret_id)
    if row is None:
        raise_not_found("Secret")
    if vault.current_role != "admin" and row.owner_id != vault.current_user_id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's entry")
    append_audit_log(session, action="secret.delete", detail=f"key={row.key}", project_id=row.project_id)
    session.delete(row)


@router.post("/{secret_id}/test-connectivity")
async def test_connectivity(
    secret_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> ConnectivityResult:
    row = session.get(Secret, secret_id)
    if row is None:
        raise_not_found("Secret")
    base_url = (row.base_url or "").strip()
    if not base_url:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "base_url required for connectivity test",
                "code": "VALIDATION_ERROR",
            },
        )
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            r = await client.head(base_url, follow_redirects=True)
            if r.status_code in (404, 405):
                r = await client.get(base_url, follow_redirects=True)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return ConnectivityResult(
                reachable=True,
                status_code=r.status_code,
                latency_ms=latency_ms,
                error=None,
            )
    except httpx.RequestError as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return ConnectivityResult(
            reachable=False,
            status_code=None,
            latency_ms=latency_ms,
            error=str(exc) or "connection failed",
        )
