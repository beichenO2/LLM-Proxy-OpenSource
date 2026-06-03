"""Append-only audit log helper."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def append_audit_log(
    session: Session,
    *,
    action: str,
    detail: str | None = None,
    project_id: str | None = None,
) -> None:
    """Insert a new audit log row; caller is responsible for committing the session."""
    row = AuditLog(
        id=str(uuid.uuid4()),
        action=action,
        detail=detail,
        project_id=project_id,
    )
    session.add(row)
