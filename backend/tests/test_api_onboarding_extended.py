"""Extended onboarding tests — migration failure path."""

from __future__ import annotations

from starlette.testclient import TestClient

from app.main import create_app


def test_init_db_migration_failure_returns_500(monkeypatch):
    """When run_migrations_to_head raises, /api/onboarding/init-db returns 500."""
    import app.api.onboarding as onboarding_mod

    def broken_migrations(database_url: str) -> None:
        raise RuntimeError("migration exploded")

    monkeypatch.setattr(onboarding_mod, "run_migrations_to_head", broken_migrations)

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as tc:
        r = tc.post("/api/onboarding/init-db")
        assert r.status_code == 500
