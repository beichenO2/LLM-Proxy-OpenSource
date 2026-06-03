"""Persisted application settings: listen port and JSON preferences (STNG-01, STNG-03)."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import AppSettings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsGetResponse(BaseModel):
    api_port: int | None
    preferences: dict


class SettingsPutBody(BaseModel):
    api_port: int | None = Field(default=None, ge=1024, le=65535)
    preferences: dict | None = None


def parse_preferences_json(raw: str | None) -> dict:
    """Safely parse a JSON string into a dict, returning ``{}`` on any failure."""
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            return loaded
    except json.JSONDecodeError:
        pass
    return {}


@router.get("")
def get_app_settings(session: Annotated[Session, Depends(get_db)]) -> SettingsGetResponse:
    """Return persisted API port and JSON object preferences.

    Changing ``api_port`` via PUT applies on the next process start (see CLI ``start``),
    not for an already-running server instance (STNG-01).
    """
    row = session.get(AppSettings, 1)
    if row is None:
        return SettingsGetResponse(api_port=None, preferences={})
    return SettingsGetResponse(
        api_port=row.api_port,
        preferences=parse_preferences_json(row.preferences_json),
    )


@router.put("")
def put_app_settings(
    body: SettingsPutBody,
    session: Annotated[Session, Depends(get_db)],
) -> SettingsGetResponse:
    """Update persisted API port and/or JSON preferences."""
    row = session.get(AppSettings, 1)
    if row is None:
        row = AppSettings(id=1, api_port=None, preferences_json="{}")
        session.add(row)
    data = body.model_dump(exclude_unset=True)
    if "api_port" in data:
        row.api_port = data["api_port"]
    if "preferences" in data:
        if data["preferences"] is None:
            row.preferences_json = "{}"
        else:
            row.preferences_json = json.dumps(data["preferences"])
    session.flush()
    session.refresh(row)
    return SettingsGetResponse(
        api_port=row.api_port,
        preferences=parse_preferences_json(row.preferences_json),
    )
