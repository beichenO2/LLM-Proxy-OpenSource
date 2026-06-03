"""End-to-end smoke tests exercising the full user journey.

Run against a live or test server — validates the complete workflow:
  vault unlock → project CRUD → secret/binding CRUD →
  template render → export → proxy → test center → logs → settings.

Uses the FastAPI TestClient (no network required).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.services.vault import VaultService


@pytest.fixture()
def smoke_client(tmp_path, monkeypatch):
    db_path = tmp_path / "smoke.db"
    monkeypatch.setenv("PRIVPORTAL_DATABASE_URL", f"sqlite:///{db_path}")

    from app.db import session as session_mod

    engine = session_mod.create_sync_engine(f"sqlite:///{db_path}")
    session_mod._engine = engine
    session_mod.SessionLocal.configure(bind=engine)

    from app.services.db_bootstrap import run_migrations_to_head

    run_migrations_to_head(f"sqlite:///{db_path}")

    from sqlalchemy.orm import Session

    with Session(engine) as s:
        VaultService.create_new_database(s, "smokepass")
        s.commit()

    app.state.vault = VaultService()

    client = TestClient(app)
    yield client

    engine.dispose()


class TestFullJourney:
    """A single sequential test that mirrors a real user session."""

    def test_complete_workflow(self, smoke_client):
        c = smoke_client

        # --- 1. Vault status & unlock ---
        r = c.get("/api/vault/status")
        assert r.status_code == 200
        assert r.json()["locked"] is True

        r = c.post("/api/vault/unlock", json={"master_password": "smokepass"})
        assert r.status_code == 200
        assert r.json()["status"] == "unlocked"

        r = c.get("/api/vault/status")
        assert r.json()["locked"] is False

        # --- 2. Onboarding status ---
        r = c.get("/api/onboarding/status")
        assert r.status_code == 200
        data = r.json()
        assert data["has_db"] is True
        assert data["has_vault"] is True

        # --- 3. Create project ---
        r = c.post("/api/projects", json={"name": "Smoke", "description": "e2e"})
        assert r.status_code == 201
        proj = r.json()
        pid = proj["id"]

        # --- 4. Dashboard summary ---
        r = c.get(f"/api/dashboard/summary?project_id={pid}")
        assert r.status_code == 200
        assert r.json()["secret_count"] == 0

        # --- 5. Create secret ---
        r = c.post("/api/secrets", json={"key": "secret.smoke.api", "value": "sk-smoke-secret-val", "project_id": pid, "base_url": "https://httpbin.org", "category": "smoke"})
        assert r.status_code == 201
        sec = r.json()
        sec_id = sec["id"]
        assert "sk-" not in sec.get("value", "")

        # --- 6. Verify secret metadata is readable without leaking plaintext ---
        r = c.get(f"/api/secrets/{sec_id}")
        assert r.status_code == 200
        assert r.json().get("value", "") != "sk-smoke-secret-val"

        # --- 7. Rotate secret ---
        r = c.post(f"/api/secrets/{sec_id}/rotate", json={"value": "sk-smoke-rotated"})
        assert r.status_code == 200
        assert r.json()["rotated_at"] is not None

        # --- 8. Create binding ---
        r = c.post("/api/bindings", json={"service_name": "smoke.httpbin", "secret_ref_key": "secret.smoke.api", "project_id": pid})
        assert r.status_code == 201
        bind = r.json()
        assert bind["resolved"] is True

        # --- 9. Template render ---
        r = c.post("/api/render", json={
            "template": "Ref: [[secret_ref.smoke.api]], bind: [[binding.smoke.httpbin]], missing: [[secret_ref.nope]]",
            "project_id": pid,
        })
        assert r.status_code == 200
        rd = r.json()
        assert "[secret_ref:" in rd["rendered"]
        assert rd["stats"]["secret_ref_rendered"] >= 1

        # --- 10. Export markdown ---
        r = c.post("/api/export", json={"template": "# Hello [[secret_ref.smoke.api]]", "project_id": pid, "format": "markdown"})
        assert r.status_code == 200
        assert "[secret_ref:" in r.text

        # --- 11. Export HTML ---
        r = c.post("/api/export", json={"template": "# Hello [[secret_ref.smoke.api]]", "project_id": pid, "format": "html"})
        assert r.status_code == 200
        assert "<html" in r.text

        # --- 12. Export TXT ---
        r = c.post("/api/export", json={"template": "**Bold** [[secret_ref.smoke.api]]", "project_id": pid, "format": "txt"})
        assert r.status_code == 200
        assert "Bold" in r.text
        assert "**" not in r.text

        # --- 13. Test Center: LLM connectivity ---
        r = c.post("/api/test-center/run", json={"test_type": "llm_connectivity"})
        assert r.status_code == 200
        for item in r.json()["results"]:
            assert item["status"] in ("pass", "fail", "skip")

        # --- 14. Logs ---
        r = c.get("/api/logs?limit=3")
        assert r.status_code == 200
        assert "items" in r.json()

        # --- 15. Audit log ---
        r = c.get("/api/audit-log?limit=5")
        assert r.status_code == 200
        actions = [x["action"] for x in r.json()["items"]]
        assert "vault.unlock" in actions
        assert "project.create" in actions

        # --- 16. Settings ---
        r = c.get("/api/settings")
        assert r.status_code == 200

        r = c.put("/api/settings", json={"api_port": 9999, "preferences": {"theme": "dark"}})
        assert r.status_code == 200
        assert r.json()["api_port"] == 9999

        r = c.get("/api/settings")
        assert r.json()["preferences"]["theme"] == "dark"

        # --- 17. Change master password ---
        r = c.post("/api/vault/change-password", json={"current_password": "smokepass", "new_password": "newsmoke"})
        assert r.status_code == 200

        r = c.post("/api/vault/unlock", json={"master_password": "smokepass"})
        assert r.json().get("code") == "AUTH_FAILED" or r.status_code != 200

        r = c.post("/api/vault/unlock", json={"master_password": "newsmoke"})
        assert r.status_code == 200

        # --- 18. Secret metadata still accessible after password change ---
        r = c.get(f"/api/secrets/{sec_id}")
        assert r.status_code == 200

        # --- 19. Error handling ---
        r = c.get("/api/projects/nonexistent")
        assert r.status_code == 404

        r = c.post("/api/render", json={"template": ""})
        assert r.status_code == 422

        r = c.post("/api/export", json={"template": "x", "format": "pdf"})
        assert r.status_code == 422

        r = c.get("/proxy/nonexistent/path")
        assert r.status_code == 404

        # --- 20. Cleanup: delete entities ---
        r = c.delete(f"/api/secrets/{sec_id}")
        assert r.status_code == 204

        r = c.delete(f"/api/projects/{pid}")
        assert r.status_code == 204

        # --- 21. Onboarding complete ---
        r = c.post("/api/onboarding/complete")
        assert r.status_code == 200

        r = c.get("/api/onboarding/status")
        assert r.json()["completed"] is True
