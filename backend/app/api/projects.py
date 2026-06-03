"""Projects REST API (PROJ-01–PROJ-03, D-31 pagination)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin_vault
from app.api.exceptions import raise_not_found
from app.db.models import Project
from app.services.audit import append_audit_log
from app.services.vault import VaultService

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectOut]
    total: int


@router.get("")
def list_projects(
    session: Annotated[Session, Depends(get_db)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=0, le=200),
) -> ProjectListResponse:
    """Return paginated project list."""
    total = session.scalar(select(func.count()).select_from(Project)) or 0
    rows = session.scalars(select(Project).offset(offset).limit(limit)).all()
    return ProjectListResponse(
        items=[ProjectOut.model_validate(r) for r in rows],
        total=int(total),
    )


@router.post("", status_code=201)
def create_project(
    body: ProjectCreate,
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_admin_vault)],
) -> ProjectOut:
    """Create a new project container and write an audit log entry."""
    pid = str(uuid.uuid4())
    row = Project(id=pid, name=body.name, description=body.description)
    session.add(row)
    session.flush()
    session.refresh(row)
    append_audit_log(session, action="project.create", detail=f"name={row.name}", project_id=row.id)
    return ProjectOut.model_validate(row)


@router.get("/{project_id}")
def get_project(
    project_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> ProjectOut:
    """Return a single project by ID."""
    row = session.get(Project, project_id)
    if row is None:
        raise_not_found("Project")
    return ProjectOut.model_validate(row)


@router.patch("/{project_id}")
def patch_project(
    project_id: str,
    body: ProjectUpdate,
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_admin_vault)],
) -> ProjectOut:
    """Partial update of a project's name or description."""
    row = session.get(Project, project_id)
    if row is None:
        raise_not_found("Project")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is None:
        raise HTTPException(
            status_code=422,
            detail={"detail": "name cannot be null", "code": "VALIDATION_ERROR"},
        )
    if "name" in data:
        row.name = data["name"]
    if "description" in data:
        row.description = data["description"]
    session.flush()
    session.refresh(row)
    return ProjectOut.model_validate(row)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_admin_vault)],
) -> None:
    """Delete a project and cascade-remove associated identities, secrets, and bindings."""
    row = session.get(Project, project_id)
    if row is None:
        raise_not_found("Project")
    append_audit_log(session, action="project.delete", detail=f"name={row.name}", project_id=row.id)
    session.delete(row)
