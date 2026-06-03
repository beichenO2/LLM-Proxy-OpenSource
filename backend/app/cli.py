"""Typer CLI: start API, run migrations, import demo data (D-13)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import logging

import typer
import uvicorn
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from typer import Typer

from app.core.config import Settings

_log = logging.getLogger(__name__)
from app.db.models import DbMetadata
from app.db.session import create_sync_engine
from app.services.demo_seed import seed_demo_data
from app.services.db_bootstrap import run_migrations_to_head
from app.services.vault import VaultService

app_cli = Typer(no_args_is_help=True)

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _resolve_master_password() -> str:
    pw = os.environ.get("PRIVPORTAL_MASTER_PASSWORD")
    if pw:
        return pw
    return typer.prompt("Master password", hide_input=True)


@app_cli.command()
def start() -> None:
    """Run the ASGI app with uvicorn (host/port from Settings).

    If Alembic migration ``004_app_settings`` is applied and row ``app_settings.id=1``
    has a non-null ``api_port``, that value overrides ``PRIVPORTAL_API_PORT`` for this
    process. Persisted port changes take effect on the next start (STNG-01). If the
    table is missing (pre-migration), environment defaults are used.
    """
    settings = Settings()
    preferred = settings.api_port
    try:
        from app.db.models import AppSettings
        from app.db.session import SessionLocal

        session = SessionLocal()
        try:
            row = session.get(AppSettings, 1)
            if row is not None and row.api_port is not None:
                preferred = row.api_port
        finally:
            session.close()
    except Exception:
        pass

    sys.path.insert(0, str(BACKEND_ROOT.parent.parent / "SOTAgent" / "sdk-port" / "python"))
    from polarisor_port_sdk import claim_port_sync, register_capabilities_sync
    port = claim_port_sync(service="polarprivate", project="PolarPrivate", preferred=preferred)

    cap_path = str(BACKEND_ROOT.parent / "capabilities.json")
    if Path(cap_path).exists():
        try:
            register_capabilities_sync(cap_path)
        except Exception as e:
            _log.warning("capability registration failed (non-fatal): %s", e)

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=port,
        factory=False,
        reload=False,
    )


@app_cli.command()
def init_db() -> None:
    """Run Alembic migrations to head (uses PRIVPORTAL_DATABASE_URL / default DB)."""
    settings = Settings()
    run_migrations_to_head(settings.database_url)


@app_cli.command()
def import_demo(
    database_url: str = typer.Option(
        "sqlite:///./privportal.db",
        "--database-url",
        help="SQLAlchemy database URL",
    ),
) -> None:
    """Initialize vault if needed, unlock, and insert demo project / identities / secret."""
    run_migrations_to_head(database_url)
    master_password = _resolve_master_password()

    engine = create_sync_engine(database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        meta = session.scalar(select(DbMetadata).where(DbMetadata.id == 1))
        if meta is None:
            VaultService.create_new_database(session, master_password)

        vault = VaultService()
        vault.unlock(session, master_password)

        seed_demo_data(session, vault)
        session.commit()
    finally:
        session.close()
        engine.dispose()


@app_cli.command(
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }
)
def test(ctx: typer.Context) -> None:
    """Run pytest from the backend tree (CLID-03).

    Forwards arguments after ``test`` (or after ``--``) to pytest, e.g.
    ``privportal test -- -k integration``. With no extra arguments, runs
    ``pytest -q``.

    Install test dependencies first: ``uv sync --extra dev``.
    """
    extra = list(ctx.args)
    if extra and extra[0] == "--":
        extra = extra[1:]

    cmd = [sys.executable, "-m", "pytest"]
    if not extra:
        cmd.append("-q")
    else:
        cmd.extend(extra)
    proc = subprocess.run(cmd, cwd=str(BACKEND_ROOT), check=False)
    raise typer.Exit(code=proc.returncode)


@app_cli.command()
def smoke() -> None:
    """Run end-to-end smoke test against a temporary database.

    Exercises the full user journey: vault → project → identity → secret → binding
    → render → export → test center → logs → settings → password change → errors.

    Uses pytest under the hood with an isolated SQLite database.
    """
    typer.echo("🔥 PrivPortal Smoke Test")
    typer.echo("=" * 40)
    cmd = [sys.executable, "-m", "pytest", "tests/test_smoke_e2e.py", "-v", "--tb=short"]
    proc = subprocess.run(cmd, cwd=str(BACKEND_ROOT), check=False)
    raise typer.Exit(code=proc.returncode)


def main() -> None:
    app_cli()


if __name__ == "__main__":
    main()
