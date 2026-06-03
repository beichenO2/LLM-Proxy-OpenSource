"""CLI smoke tests (CLID-01, CLID-02)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli import app_cli

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_start_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app_cli, ["start", "--help"])
    assert result.exit_code == 0
    out = (result.stdout or "").lower()
    assert "host" in out or "port" in out or "uvicorn" in out


def test_init_db_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "init_mig.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("PRIVPORTAL_DATABASE_URL", url)
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli", "init-db"],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_import_demo_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "demo.db"
    url = f"sqlite:///{db_file}"
    monkeypatch.setenv("PRIVPORTAL_MASTER_PASSWORD", "pytest-demo-mpw-999")
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli", "import-demo", "--database-url", url],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert db_file.exists()
    conn = sqlite3.connect(db_file)
    try:
        row = conn.execute("SELECT COUNT(*) FROM projects").fetchone()
        assert row is not None and row[0] >= 1
    finally:
        conn.close()


def test_privportal_test_command() -> None:
    """CLI `test` runs pytest subprocess (collect-only keeps CI fast)."""
    proc = subprocess.run(
        [sys.executable, "-m", "app.cli", "test", "--", "--collect-only"],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
