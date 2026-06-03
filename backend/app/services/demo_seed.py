"""Shared demo project seeding for CLI ``import-demo`` and HTTP ``/api/onboarding/import-demo`` (D-110)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Binding, Project, Secret
from app.services.vault import VaultService

DEMO_PROJECT_NAME = "Demo Project"


def seed_demo_data(session: Session, vault: VaultService) -> dict:
    """Create or skip the demo project: 1 secret, 1 binding (Aliyun only; CTYun removed).

    Idempotent: if a project named ``Demo Project`` already exists, returns its id and
    current row counts without inserting duplicates. Caller must ``commit`` when appropriate
    (CLI commits after this call; FastAPI ``get_db`` commits on success).
    """
    existing = session.scalar(select(Project).where(Project.name == DEMO_PROJECT_NAME))
    if existing is not None:
        pid = existing.id
        ns = session.scalar(select(func.count()).select_from(Secret).where(Secret.project_id == pid))
        nb = session.scalar(select(func.count()).select_from(Binding).where(Binding.project_id == pid))
        return {
            "project_id": pid,
            "secrets": int(ns or 0),
            "bindings": int(nb or 0),
        }

    project_id = str(uuid.uuid4())
    session.add(
        Project(
            id=project_id,
            name=DEMO_PROJECT_NAME,
            description="Demo import (D-110): Aliyun CodingPlan binding only.",
        )
    )

    session.add(
        Secret(
            id=str(uuid.uuid4()),
            project_id=project_id,
            key="secret.aliyun.CodingPlan.api_key",
            value=vault.encrypt_secret_value("demo-codingplan-api-key-placeholder"),
            category="proxy",
            base_url="https://coding.dashscope.aliyuncs.com/v1",
        )
    )

    session.add(
        Binding(
            id=str(uuid.uuid4()),
            project_id=project_id,
            service_name="llm.aliyun.codingplan",
            secret_ref_key="secret.aliyun.CodingPlan.api_key",
        )
    )

    return {"project_id": project_id, "secrets": 1, "bindings": 1}
