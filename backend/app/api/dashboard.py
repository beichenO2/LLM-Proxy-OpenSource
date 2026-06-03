"""Dashboard summary and audit log API (DASH-01)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_unlocked_vault
from app.db.models import AuditLog, Binding, Project, Secret
from app.services.vault import VaultService

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])
audit_router = APIRouter(prefix="/audit-log", tags=["audit"])


class DashboardSummaryResponse(BaseModel):
    secret_count: int
    binding_count: int
    project_id: str | None


class AuditLogItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action: str
    detail: str | None
    project_id: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItemOut]


def _count_rows(
    session: Session,
    model: type[Secret] | type[Binding],
    project_id: str | None,
    vault: VaultService | None = None,
) -> int:
    stmt = select(func.count()).select_from(model)
    if project_id is not None:
        stmt = stmt.where(model.project_id == project_id)
    if vault and vault.current_role != "admin" and hasattr(model, "owner_id"):
        stmt = stmt.where(model.owner_id == vault.current_user_id)
    return int(session.scalar(stmt) or 0)


@dashboard_router.get("/summary")
def dashboard_summary(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
    project_id: str | None = None,
) -> DashboardSummaryResponse:
    """Return secret and binding counts for the dashboard overview."""
    return DashboardSummaryResponse(
        secret_count=_count_rows(session, Secret, project_id, vault),
        binding_count=_count_rows(session, Binding, project_id, vault),
        project_id=project_id,
    )


class RecentProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class RecentProjectsResponse(BaseModel):
    items: list[RecentProjectOut]


@dashboard_router.get("/recent-projects")
def recent_projects(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> RecentProjectsResponse:
    """Return the union of the 10 most recent projects and any project created in the last hour.

    Non-admin users only see projects that contain their own secrets.
    """
    from datetime import timedelta, timezone

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    is_admin = vault.current_role == "admin"

    if is_admin:
        base_stmt = select(Project)
    else:
        uid = vault.current_user_id
        owned_project_ids = (
            select(Secret.project_id).where(Secret.owner_id == uid)
        ).subquery()
        base_stmt = select(Project).where(Project.id.in_(select(owned_project_ids)))

    recent_by_time = session.scalars(
        base_stmt.order_by(Project.created_at.desc()).limit(10)
    ).all()

    recent_by_hour = session.scalars(
        base_stmt.where(Project.created_at >= one_hour_ago)
    ).all()

    seen_ids: set[str] = set()
    merged: list[RecentProjectOut] = []
    for row in recent_by_time:
        if row.id not in seen_ids:
            seen_ids.add(row.id)
            merged.append(RecentProjectOut.model_validate(row))
    for row in recent_by_hour:
        if row.id not in seen_ids:
            seen_ids.add(row.id)
            merged.append(RecentProjectOut.model_validate(row))

    merged.sort(key=lambda p: p.created_at, reverse=True)
    return RecentProjectsResponse(items=merged)


class RecentEntryOut(BaseModel):
    id: str
    type: str
    key: str
    value: str | None
    has_value: bool
    project_id: str | None
    category: str | None
    created_at: datetime


class RecentEntriesResponse(BaseModel):
    items: list[RecentEntryOut]
    total: int


@dashboard_router.get("/recent-entries")
def recent_entries(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> RecentEntriesResponse:
    """Return the union of the 10 most recent secrets and any secret created in the last hour.

    Secrets are shown with keys only, no values.
    Designed for the dashboard so users can quickly find keys that Agents just added.
    """
    from datetime import timedelta, timezone

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    is_admin = vault.current_role == "admin"
    uid = vault.current_user_id

    sec_base = select(Secret)
    if not is_admin:
        sec_base = sec_base.where(Secret.owner_id == uid)
    sec_recent = session.scalars(
        sec_base.order_by(Secret.created_at.desc()).limit(10)
    ).all()
    sec_hourly = session.scalars(
        sec_base.where(Secret.created_at >= one_hour_ago)
    ).all()

    seen: set[str] = set()
    merged: list[RecentEntryOut] = []

    def add_secret(row: Secret) -> None:
        if row.id in seen:
            return
        seen.add(row.id)
        has_val = bool(row.value and row.value.strip())
        merged.append(RecentEntryOut(
            id=row.id, type="secret", key=row.key, value=None,
            has_value=has_val,
            project_id=row.project_id, category=row.category, created_at=row.created_at,
        ))

    for r in sec_recent:
        add_secret(r)
    for r in sec_hourly:
        add_secret(r)

    merged.sort(key=lambda e: e.created_at, reverse=True)
    return RecentEntriesResponse(items=merged, total=len(merged))


@audit_router.get("")
def list_audit_log(
    session: Annotated[Session, Depends(get_db)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    project_id: str | None = None,
) -> AuditLogListResponse:
    """Return recent audit log entries ordered by creation time descending."""
    stmt = select(AuditLog)
    if project_id is not None:
        stmt = stmt.where(AuditLog.project_id == project_id)
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    rows = session.scalars(stmt).all()
    return AuditLogListResponse(
        items=[AuditLogItemOut.model_validate(r) for r in rows]
    )
