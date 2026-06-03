"""Standardized JSON error responses (D-32) and structlog error logging (D-33)."""

from __future__ import annotations

from typing import NoReturn

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

_LOG = structlog.get_logger(__name__)


def raise_not_found(entity: str) -> NoReturn:
    """Raise a 404 HTTPException with a standard ENTITY_NOT_FOUND body."""
    raise HTTPException(
        status_code=404,
        detail={"detail": f"{entity} not found", "code": "ENTITY_NOT_FOUND"},
    )


def raise_duplicate(entity: str) -> NoReturn:
    """Raise a 409 HTTPException with a standard DUPLICATE_KEY body."""
    raise HTTPException(
        status_code=409,
        detail={"detail": f"duplicate {entity}", "code": "DUPLICATE_KEY"},
    )


def _http_error_body(exc: HTTPException) -> dict[str, object]:
    detail = exc.detail
    if isinstance(detail, dict) and "detail" in detail and "code" in detail:
        return {k: v for k, v in detail.items()}
    if isinstance(detail, str):
        return {"detail": detail, "code": "HTTP_ERROR"}
    return {"detail": str(detail), "code": "HTTP_ERROR"}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        body = _http_error_body(exc)
        _LOG.warning(
            "http_error",
            status_code=exc.status_code,
            code=body.get("code"),
            detail=body.get("detail"),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=body,
        )

    @app.exception_handler(Exception)
    def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        """Catch-all: never expose raw exception text — it may contain secrets."""
        _LOG.error(
            "unhandled_exception",
            exc_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "code": "INTERNAL_ERROR"},
        )
