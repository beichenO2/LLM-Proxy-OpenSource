"""Shared Alembic migration bootstrap (CLI and HTTP onboarding)."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def run_migrations_to_head(database_url: str) -> None:
    """Apply migrations to ``head``; temporarily sets ``PRIVPORTAL_DATABASE_URL`` for env.py."""
    previous = os.environ.get("PRIVPORTAL_DATABASE_URL")
    try:
        os.environ["PRIVPORTAL_DATABASE_URL"] = database_url
        cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
        command.upgrade(cfg, "head")
    finally:
        if previous is not None:
            os.environ["PRIVPORTAL_DATABASE_URL"] = previous
        else:
            os.environ.pop("PRIVPORTAL_DATABASE_URL", None)
