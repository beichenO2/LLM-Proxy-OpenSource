"""Tests for exception handlers — dict detail, string detail, and unhandled exceptions."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import HTTPException

from app.api.exceptions import _http_error_body


def test_http_error_body_dict_with_detail_and_code():
    exc = HTTPException(status_code=409, detail={"detail": "duplicate key", "code": "DUPLICATE_KEY"})
    body = _http_error_body(exc)
    assert body["detail"] == "duplicate key"
    assert body["code"] == "DUPLICATE_KEY"


def test_http_error_body_string_detail():
    exc = HTTPException(status_code=400, detail="bad request")
    body = _http_error_body(exc)
    assert body["detail"] == "bad request"
    assert body["code"] == "HTTP_ERROR"


def test_http_error_body_other_type():
    exc = HTTPException(status_code=500, detail=["some", "list"])
    body = _http_error_body(exc)
    assert "some" in body["detail"]
    assert body["code"] == "HTTP_ERROR"


def test_http_error_body_dict_missing_code():
    """Dict detail without 'code' key falls through to string conversion."""
    exc = HTTPException(status_code=400, detail={"detail": "oops"})
    body = _http_error_body(exc)
    assert "oops" in body["detail"]
    assert body["code"] == "HTTP_ERROR"


def test_unhandled_exception_returns_500():
    """Force a 500 by raising a non-HTTP exception in a route."""
    from pathlib import Path

    from app.main import create_app
    from starlette.testclient import TestClient

    with patch.object(Path, "is_dir", return_value=False):
        app = create_app()

    @app.get("/test-crash")
    def crash():
        raise RuntimeError("unexpected")

    with TestClient(app, raise_server_exceptions=False) as tc:
        r = tc.get("/test-crash")
        assert r.status_code == 500
        data = r.json()
        assert data["code"] == "INTERNAL_ERROR"
        assert "unexpected" not in data["detail"]


def test_http_exception_string_detail_via_api():
    """HTTPException with plain string detail is normalized to {detail, code}."""
    from pathlib import Path

    from app.main import create_app
    from starlette.testclient import TestClient

    with patch.object(Path, "is_dir", return_value=False):
        app = create_app()

    @app.get("/test-string-error")
    def string_error():
        raise HTTPException(status_code=400, detail="plain string error")

    with TestClient(app, raise_server_exceptions=False) as tc:
        r = tc.get("/test-string-error")
        assert r.status_code == 400
        data = r.json()
        assert data["detail"] == "plain string error"
        assert data["code"] == "HTTP_ERROR"
