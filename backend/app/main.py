"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse

from app.api import bindings as bindings_routes
from app.api import dashboard as dashboard_routes
from app.api import export as export_routes
from app.api import logs as logs_routes
from app.api import onboarding as onboarding_routes
from app.api import projects as projects_routes
from app.api import proxy as proxy_routes
from app.api import v1_gateway as v1_gateway_routes
from app.api import render as render_routes
from app.api import secrets as secrets_routes
from app.api import settings as settings_routes
from app.api import test_center as test_center_routes
from app.api import user_accounts as user_accounts_routes
from app.api import identity_bindings as identity_bindings_routes
from app.api import vault_routes
from app.api import sanitize as sanitize_routes
from app.api import auth as auth_routes
from app.api import sign as sign_routes
from app.api import d_class as d_class_routes
from app.api import vault_sync as vault_sync_routes
from app.api.exceptions import register_exception_handlers
from app.logging_config import configure_logging
from app.services.vault import VaultService
from sqlalchemy import select
from sqlalchemy.orm import Session


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    from app.db.session import SessionLocal

    vault: VaultService = app.state.vault
    session = SessionLocal()
    try:
        if vault.try_auto_unlock(session):
            session.commit()
            from app.logging_config import get_logger
            get_logger(__name__).info("vault_auto_unlocked")
            migrate_identity_encryption(session, vault)

        from app.db.models import CustomPiiPattern
        from app.services.pii_scanner import load_custom_patterns_from_db
        try:
            rows = session.query(CustomPiiPattern).all()
            if rows:
                db_patterns = [(r.label, r.description, r.pattern) for r in rows]
                loaded = load_custom_patterns_from_db(db_patterns)
                if loaded > 0:
                    from app.logging_config import get_logger
                    get_logger(__name__).info("loaded_custom_pii_patterns", count=loaded)
        except Exception:
            pass

        from app.services.browser_session import cleanup_expired
        cleaned = cleanup_expired(session)
        session.commit()
        if cleaned > 0:
            from app.logging_config import get_logger
            get_logger(__name__).info("cleaned_expired_sessions", count=cleaned)
    except Exception:
        from app.logging_config import get_logger
        get_logger(__name__).exception("startup_init_error")
        session.rollback()
    finally:
        session.close()

    app.state.httpx_client = httpx.AsyncClient(
        trust_env=False,
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=30,
        ),
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0),
        follow_redirects=True,
    )
    try:
        yield
    finally:
        await app.state.httpx_client.aclose()


def migrate_identity_encryption(session: Session, vault: VaultService) -> int:
    """Deprecated: Identity encryption migration (Identity model removed)."""
    return 0


def create_app() -> FastAPI:
    """Build the FastAPI application with all routes, middleware, and exception handlers."""
    app = FastAPI(title="PrivPortal", lifespan=lifespan)
    app.state.vault = VaultService()
    register_exception_handlers(app)
    allowed_origins = [
        "http://127.0.0.1:5170",
        "http://localhost:5170",
    ]
    funnel_origin = os.environ.get("FUNNEL_ORIGIN")
    if funnel_origin:
        allowed_origins.append(funnel_origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "vault_unlocked": app.state.vault.is_unlocked,
        }

    app.include_router(vault_routes.router, prefix="/api")
    app.include_router(settings_routes.router, prefix="/api")
    app.include_router(dashboard_routes.dashboard_router, prefix="/api")
    app.include_router(dashboard_routes.audit_router, prefix="/api")
    app.include_router(logs_routes.router, prefix="/api")
    app.include_router(onboarding_routes.router, prefix="/api")
    app.include_router(projects_routes.router, prefix="/api")
    app.include_router(secrets_routes.router, prefix="/api")
    app.include_router(bindings_routes.router, prefix="/api")
    app.include_router(render_routes.router, prefix="/api")
    app.include_router(export_routes.router, prefix="/api")
    app.include_router(proxy_routes.router, prefix="/proxy")
    app.include_router(v1_gateway_routes.router, prefix="/v1")
    app.include_router(test_center_routes.router, prefix="/api")
    app.include_router(user_accounts_routes.router, prefix="/api")
    app.include_router(identity_bindings_routes.router, prefix="/api")
    app.include_router(sanitize_routes.router, prefix="/api")
    app.include_router(auth_routes.router, prefix="/api")
    app.include_router(sign_routes.router, prefix="")
    app.include_router(d_class_routes.router, prefix="/api")
    app.include_router(vault_sync_routes.router, prefix="/api")

    # ─── 生产模式：serve 前端构建产物 ───────────────────────
    # 当 frontend/dist 存在时，自动挂载静态文件并提供 SPA catch-all
    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        index_html = frontend_dist / "index.html"

        # 静态资源（JS/CSS/images 等）
        assets_dir = frontend_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

        # 其他根级静态文件（favicon 等）
        app.mount("/static-root", StaticFiles(directory=str(frontend_dist)), name="static-root")

        # SPA catch-all：非 API/proxy/health 路径返回 index.html
        @app.get("/{path:path}")
        async def spa_catch_all(path: str) -> FileResponse:
            candidate = frontend_dist / path
            if candidate.is_file() and ".." not in path:
                return FileResponse(str(candidate))
            return FileResponse(str(index_html))

    return app


app = create_app()
