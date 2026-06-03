"""Onboarding HTTP API (D-108, D-109, D-111) and DB init (ONBD-02)."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_unlocked_vault
from app.api.settings import parse_preferences_json
from app.core.config import Settings
from app.db.models import AppSettings, DbMetadata
from app.services.db_bootstrap import run_migrations_to_head
from app.services.demo_seed import seed_demo_data
from app.services.vault import VaultService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingStatusResponse(BaseModel):
    completed: bool
    has_db: bool
    has_vault: bool


@router.get("/status", response_model=OnboardingStatusResponse)
def onboarding_status(session: Annotated[Session, Depends(get_db)]) -> OnboardingStatusResponse:
    """Check whether DB, vault, and onboarding wizard are initialized."""
    inspector = sa_inspect(session.bind)
    has_db = "db_metadata" in inspector.get_table_names()
    has_vault = False
    if has_db:
        meta = session.get(DbMetadata, 1)
        has_vault = meta is not None and meta.sentinel_ciphertext is not None
    completed = False
    if has_db:
        row = session.get(AppSettings, 1)
        if row:
            prefs = parse_preferences_json(row.preferences_json)
            completed = bool(prefs.get("onboarding_completed"))
    return OnboardingStatusResponse(completed=completed, has_db=has_db, has_vault=has_vault)


class OkResponse(BaseModel):
    ok: bool


@router.post("/complete", response_model=OkResponse)
def onboarding_complete(session: Annotated[Session, Depends(get_db)]) -> OkResponse:
    """Mark the onboarding wizard as completed in app preferences."""
    row = session.get(AppSettings, 1)
    prefs = parse_preferences_json(row.preferences_json if row else None)
    prefs["onboarding_completed"] = True
    if row is None:
        session.add(AppSettings(id=1, api_port=None, preferences_json=json.dumps(prefs)))
    else:
        row.preferences_json = json.dumps(prefs)
    return OkResponse(ok=True)


@router.post("/init-db", response_model=OkResponse)
def onboarding_init_db() -> OkResponse:
    """Run Alembic migrations to head to initialize the database schema."""
    settings = Settings()
    try:
        run_migrations_to_head(settings.database_url)
    except Exception:
        logger.exception("onboarding init-db migration failed")
        raise HTTPException(status_code=500, detail="migration failed") from None
    return OkResponse(ok=True)


@router.post("/import-demo")
def onboarding_import_demo(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> dict:
    """Seed a demo project with sample secrets and bindings."""
    return seed_demo_data(session, vault)
