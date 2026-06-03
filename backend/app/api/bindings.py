"""Binding entries API (BIND-01–BIND-04, D-28–D-29).

R10: Fallback chain support for multi-key rotation and cross-provider failover.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.exceptions import raise_duplicate, raise_not_found
from app.db.models import Binding, Secret

router = APIRouter(prefix="/bindings", tags=["bindings"])


def _dot_notation_ref(v: str) -> str:
    if "." not in v:
        raise ValueError("secret_ref_key must use dot notation (contain at least one '.')")
    return v


class BindingCreate(BaseModel):
    service_name: str = Field(min_length=1, max_length=255)
    secret_ref_key: str = Field(min_length=1, max_length=512)
    project_id: str | None = None
    auth_header: str | None = Field(default=None, max_length=255)

    @field_validator("secret_ref_key")
    @classmethod
    def secret_ref_dot_notation(cls, v: str) -> str:
        return _dot_notation_ref(v)

    @field_validator("auth_header")
    @classmethod
    def auth_header_non_empty_if_set(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("auth_header must not be empty when set")
        return s


class BindingUpdate(BaseModel):
    service_name: str | None = Field(default=None, min_length=1, max_length=255)
    secret_ref_key: str | None = Field(default=None, min_length=1, max_length=512)
    project_id: str | None = None
    auth_header: str | None = Field(default=None, max_length=255)

    @field_validator("secret_ref_key")
    @classmethod
    def secret_ref_dot_notation(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _dot_notation_ref(v)

    @field_validator("auth_header")
    @classmethod
    def auth_header_non_empty_if_set(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("auth_header must not be empty when set")
        return s


class BindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    service_name: str
    secret_ref_key: str
    auth_header: str | None
    project_id: str | None
    resolved: bool
    proxy_url: str
    # R10: Fallback chain fields
    fallback_chain: list[str] | None = None
    priority: int = 1
    cooldown_until: datetime | None = None
    consecutive_failures: int = 0
    created_at: datetime
    updated_at: datetime


class FallbackConfig(BaseModel):
    """Fallback chain configuration for a binding."""
    fallback_chain: list[str] | None = Field(default=None, description="List of service_name to try on failure")
    priority: int | None = Field(default=None, ge=1, le=100, description="Weight for load balancing")


class BindingStatus(BaseModel):
    """Runtime status of a binding."""
    id: str
    service_name: str
    is_cooling_down: bool
    cooldown_until: datetime | None = None
    consecutive_failures: int = 0
    fallback_chain: list[str] | None = None


class BindingListResponse(BaseModel):
    items: list[BindingOut]
    total: int


def compute_resolved(session: Session, secret_ref_key: str) -> bool:
    """True iff a Secret with this key exists and is enabled (D-29)."""
    exists = session.scalar(
        select(Secret.id).where(Secret.key == secret_ref_key, Secret.enabled.is_(True)).limit(1)
    )
    return exists is not None


def _assert_unique_binding_service(
    session: Session,
    project_id: str | None,
    service_name: str,
    exclude_id: str | None = None,
) -> None:
    """Enforce uniqueness of (project_id, service_name), mirroring identities."""
    stmt = select(Binding).where(Binding.service_name == service_name)
    if project_id is None:
        stmt = stmt.where(Binding.project_id.is_(None))
    else:
        stmt = stmt.where(Binding.project_id == project_id)
    if exclude_id is not None:
        stmt = stmt.where(Binding.id != exclude_id)
    row = session.scalars(stmt).first()
    if row is not None:
        raise_duplicate("binding service name")


def _build_proxy_url(row: Binding) -> str:
    url = f"http://127.0.0.1:12790/proxy/{row.service_name}"
    if row.project_id is not None:
        url += f"?project_id={row.project_id}"
    return url


def binding_to_out(session: Session, row: Binding) -> BindingOut:
    # Parse fallback_chain JSON
    fallback_list: list[str] | None = None
    if row.fallback_chain:
        try:
            fallback_list = json.loads(row.fallback_chain)
            if not isinstance(fallback_list, list):
                fallback_list = None
        except (json.JSONDecodeError, TypeError):
            fallback_list = None

    return BindingOut(
        id=row.id,
        service_name=row.service_name,
        secret_ref_key=row.secret_ref_key,
        auth_header=row.auth_header,
        project_id=row.project_id,
        resolved=compute_resolved(session, row.secret_ref_key),
        proxy_url=_build_proxy_url(row),
        fallback_chain=fallback_list,
        priority=row.priority,
        cooldown_until=row.cooldown_until,
        consecutive_failures=row.consecutive_failures,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("")
def list_bindings(
    session: Annotated[Session, Depends(get_db)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=0, le=200),
    project_id: str | None = None,
) -> BindingListResponse:
    """Return paginated binding entries with computed ``resolved`` status."""
    list_stmt = select(Binding)
    count_stmt = select(func.count()).select_from(Binding)
    if project_id is not None:
        w = Binding.project_id == project_id
        list_stmt = list_stmt.where(w)
        count_stmt = count_stmt.where(w)
    total = session.scalar(count_stmt) or 0
    rows = session.scalars(list_stmt.offset(offset).limit(limit)).all()
    return BindingListResponse(
        items=[binding_to_out(session, r) for r in rows],
        total=int(total),
    )


@router.post("", status_code=201)
def create_binding(
    body: BindingCreate,
    session: Annotated[Session, Depends(get_db)],
) -> BindingOut:
    """Create a service-to-secret binding for proxy forwarding."""
    _assert_unique_binding_service(session, body.project_id, body.service_name)
    bid = str(uuid.uuid4())
    row = Binding(
        id=bid,
        project_id=body.project_id,
        service_name=body.service_name,
        secret_ref_key=body.secret_ref_key,
        auth_header=body.auth_header,
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    return binding_to_out(session, row)


@router.get("/{binding_id}")
def get_binding(
    binding_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> BindingOut:
    """Return a single binding by ID."""
    row = session.get(Binding, binding_id)
    if row is None:
        raise_not_found("Binding")
    return binding_to_out(session, row)


@router.patch("/{binding_id}")
def patch_binding(
    binding_id: str,
    body: BindingUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> BindingOut:
    """Partial update of a binding entry."""
    row = session.get(Binding, binding_id)
    if row is None:
        raise_not_found("Binding")
    data = body.model_dump(exclude_unset=True)
    if "secret_ref_key" in data and data["secret_ref_key"] is None:
        raise HTTPException(
            status_code=422,
            detail={"detail": "secret_ref_key cannot be null", "code": "VALIDATION_ERROR"},
        )
    if "service_name" in data and data["service_name"] is None:
        raise HTTPException(
            status_code=422,
            detail={"detail": "service_name cannot be null", "code": "VALIDATION_ERROR"},
        )
    if "service_name" in data or "project_id" in data:
        new_name = data.get("service_name", row.service_name)
        new_pid = data["project_id"] if "project_id" in data else row.project_id
        _assert_unique_binding_service(session, new_pid, new_name, exclude_id=binding_id)
    if "service_name" in data:
        row.service_name = data["service_name"]
    if "secret_ref_key" in data:
        row.secret_ref_key = data["secret_ref_key"]
    if "auth_header" in data:
        row.auth_header = data["auth_header"]
    if "project_id" in data:
        row.project_id = data["project_id"]
    session.flush()
    session.refresh(row)
    return binding_to_out(session, row)


@router.delete("/{binding_id}", status_code=204)
def delete_binding(binding_id: str, session: Annotated[Session, Depends(get_db)]) -> None:
    """Delete a binding by ID."""
    row = session.get(Binding, binding_id)
    if row is None:
        raise_not_found("Binding")
    session.delete(row)


# ============================================================================
# R10: Fallback Chain API
# ============================================================================


@router.get("/{binding_id}/fallback")
def get_binding_fallback(
    binding_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> FallbackConfig:
    """Get fallback chain configuration for a binding."""
    row = session.get(Binding, binding_id)
    if row is None:
        raise_not_found("Binding")

    fallback_list: list[str] | None = None
    if row.fallback_chain:
        try:
            fallback_list = json.loads(row.fallback_chain)
            if not isinstance(fallback_list, list):
                fallback_list = None
        except (json.JSONDecodeError, TypeError):
            fallback_list = None

    return FallbackConfig(
        fallback_chain=fallback_list,
        priority=row.priority,
    )


@router.put("/{binding_id}/fallback")
def set_binding_fallback(
    binding_id: str,
    body: FallbackConfig,
    session: Annotated[Session, Depends(get_db)],
) -> BindingOut:
    """Set fallback chain configuration for a binding.

    Args:
        binding_id: The binding ID
        body: Fallback configuration with:
            - fallback_chain: List of service_name strings to try on failure
            - priority: Weight for load balancing (higher = more traffic)

    The fallback_chain should contain service_name of other bindings.
    On failure (429/5xx), the proxy will try each binding in order.
    """
    row = session.get(Binding, binding_id)
    if row is None:
        raise_not_found("Binding")

    # Validate fallback bindings exist
    if body.fallback_chain:
        for fb_name in body.fallback_chain:
            fb_binding = session.scalars(
                select(Binding).where(Binding.service_name == fb_name)
            ).first()
            if fb_binding is None:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "detail": f"Fallback binding '{fb_name}' not found",
                        "code": "FALLBACK_BINDING_NOT_FOUND",
                    },
                )
            # Prevent circular fallback
            if fb_binding.id == binding_id:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "detail": "Binding cannot fallback to itself",
                        "code": "CIRCULAR_FALLBACK",
                    },
                )
        row.fallback_chain = json.dumps(body.fallback_chain)
    else:
        row.fallback_chain = None

    if body.priority is not None:
        row.priority = body.priority

    session.flush()
    session.refresh(row)
    return binding_to_out(session, row)


@router.get("/{binding_id}/status")
def get_binding_status(
    binding_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> BindingStatus:
    """Get runtime status of a binding (cooldown state, failure count)."""
    row = session.get(Binding, binding_id)
    if row is None:
        raise_not_found("Binding")

    is_cooling = (
        row.cooldown_until is not None
        and row.cooldown_until > datetime.utcnow()
    )

    fallback_list: list[str] | None = None
    if row.fallback_chain:
        try:
            fallback_list = json.loads(row.fallback_chain)
            if not isinstance(fallback_list, list):
                fallback_list = None
        except (json.JSONDecodeError, TypeError):
            fallback_list = None

    return BindingStatus(
        id=row.id,
        service_name=row.service_name,
        is_cooling_down=is_cooling,
        cooldown_until=row.cooldown_until,
        consecutive_failures=row.consecutive_failures,
        fallback_chain=fallback_list,
    )


@router.post("/{binding_id}/reset-cooldown", status_code=200)
def reset_binding_cooldown(
    binding_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Manually reset cooldown for a binding.

    Use this to immediately re-enable a binding that's in cooldown.
    """
    row = session.get(Binding, binding_id)
    if row is None:
        raise_not_found("Binding")

    row.cooldown_until = None
    row.consecutive_failures = 0
    session.flush()

    return {
        "ok": True,
        "binding_id": binding_id,
        "service_name": row.service_name,
        "cooldown_until": None,
        "consecutive_failures": 0,
    }
