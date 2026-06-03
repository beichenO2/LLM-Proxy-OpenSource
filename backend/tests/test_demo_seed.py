"""Tests for demo_seed.seed_demo_data — idempotency, content verification."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import DbMetadata, Project
from app.services.demo_seed import DEMO_PROJECT_NAME, seed_demo_data
from app.services.vault import VaultService


def test_seed_demo_creates_project_and_data(db_session):
    """First call creates project with secrets and bindings."""
    if db_session.scalar(select(DbMetadata).where(DbMetadata.id == 1)) is None:
        VaultService.create_new_database(db_session, "test-master-password")

    vault = VaultService()
    vault.unlock(db_session, "test-master-password")

    result = seed_demo_data(db_session, vault)
    db_session.commit()

    assert result["secrets"] >= 2
    assert result["bindings"] >= 2
    assert result["project_id"] is not None

    project = db_session.scalar(select(Project).where(Project.name == DEMO_PROJECT_NAME))
    assert project is not None
    assert project.id == result["project_id"]


def test_seed_demo_idempotent_second_call(db_session):
    """Second call returns existing counts without inserting duplicates."""
    if db_session.scalar(select(DbMetadata).where(DbMetadata.id == 1)) is None:
        VaultService.create_new_database(db_session, "test-master-password")

    vault = VaultService()
    vault.unlock(db_session, "test-master-password")

    first = seed_demo_data(db_session, vault)
    db_session.commit()

    second = seed_demo_data(db_session, vault)

    assert second["project_id"] == first["project_id"]
    assert second["secrets"] == first["secrets"]
    assert second["bindings"] == first["bindings"]

    project_count = len(
        db_session.scalars(select(Project).where(Project.name == DEMO_PROJECT_NAME)).all()
    )
    assert project_count == 1
