"""Test db_bootstrap module — migration runner with env var cleanup."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_run_migrations_cleans_env_when_previously_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When PRIVPORTAL_DATABASE_URL was not set before, it is removed after migration."""
    monkeypatch.delenv("PRIVPORTAL_DATABASE_URL", raising=False)

    db_path = tmp_path / "bootstrap_test.db"
    url = f"sqlite:///{db_path}"

    from app.services.db_bootstrap import run_migrations_to_head

    run_migrations_to_head(url)

    assert "PRIVPORTAL_DATABASE_URL" not in os.environ
