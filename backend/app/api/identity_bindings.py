"""Cross-service identity bindings API — maps external service usernames to local user_id."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_unlocked_vault
from app.db.models import IdentityBinding, UserAccount
from app.services.audit import append_audit_log
from app.services.vault import VaultService

router = APIRouter(prefix="/identity-bindings", tags=["identity-bindings"])


class BindingCreate(BaseModel):
    user_id: str
    service: str = Field(min_length=1, max_length=128, examples=["clock", "knowlever", "polarclaw", "feishu"])
    external_username: str = Field(min_length=1, max_length=512)
    display_name: str | None = None
    metadata_json: str | None = None


class BindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    service: str
    external_username: str
    display_name: str | None
    metadata_json: str | None
    created_at: datetime
    updated_at: datetime


class BindingListResponse(BaseModel):
    items: list[BindingOut]
    total: int


class ResolveResult(BaseModel):
    user_id: str
    username: str
    service: str
    external_username: str


class ResolveNotFound(BaseModel):
    detail: str = "No binding found for the given service and external username"


@router.get("", summary="List all identity bindings")
def list_bindings(
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_unlocked_vault)],
    service: str | None = Query(None, description="Filter by service name"),
    user_id: str | None = Query(None, description="Filter by user_id"),
) -> BindingListResponse:
    stmt = select(IdentityBinding)
    if service:
        stmt = stmt.where(IdentityBinding.service == service)
    if user_id:
        stmt = stmt.where(IdentityBinding.user_id == user_id)

    rows = list(session.scalars(stmt).all())
    return BindingListResponse(
        items=[BindingOut.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.post("", status_code=201, summary="Create an identity binding")
def create_binding(
    body: BindingCreate,
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> BindingOut:
    user = session.get(UserAccount, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    existing = session.scalar(
        select(IdentityBinding).where(
            IdentityBinding.service == body.service,
            IdentityBinding.external_username == body.external_username,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": f"Binding already exists for {body.service}:{body.external_username}",
                "code": "DUPLICATE_BINDING",
                "existing_user_id": existing.user_id,
            },
        )

    if body.metadata_json:
        try:
            json.loads(body.metadata_json)
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="metadata_json must be valid JSON")

    row = IdentityBinding(
        id=str(uuid.uuid4()),
        user_id=body.user_id,
        service=body.service,
        external_username=body.external_username,
        display_name=body.display_name,
        metadata_json=body.metadata_json,
    )
    session.add(row)
    session.flush()
    append_audit_log(
        session,
        action="identity_binding.create",
        detail=f"service={body.service} external={body.external_username} user={body.user_id}",
    )
    return BindingOut.model_validate(row)


@router.delete("/{binding_id}", status_code=204, summary="Delete an identity binding")
def delete_binding(
    binding_id: str,
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> None:
    row = session.get(IdentityBinding, binding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Binding not found")
    append_audit_log(
        session,
        action="identity_binding.delete",
        detail=f"service={row.service} external={row.external_username}",
    )
    session.delete(row)


@router.get(
    "/resolve",
    summary="Resolve external identity to polarisor user_id",
    responses={404: {"model": ResolveNotFound}},
)
def resolve_user(
    service: str,
    external_username: str,
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> ResolveResult:
    """Core federation endpoint: given (service, external_username), return the polarisor user_id."""
    binding = session.scalar(
        select(IdentityBinding).where(
            IdentityBinding.service == service,
            IdentityBinding.external_username == external_username,
        )
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="No binding found for the given service and external username")

    user = session.get(UserAccount, binding.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Bound user no longer exists")

    return ResolveResult(
        user_id=user.id,
        username=user.username,
        service=binding.service,
        external_username=binding.external_username,
    )


@router.get(
    "/user/{user_id}",
    summary="List all services bound to a user",
)
def list_user_bindings(
    user_id: str,
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> BindingListResponse:
    user = session.get(UserAccount, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    rows = list(
        session.scalars(
            select(IdentityBinding).where(IdentityBinding.user_id == user_id)
        ).all()
    )
    return BindingListResponse(
        items=[BindingOut.model_validate(r) for r in rows],
        total=len(rows),
    )
