"""Tests for D-class controlled channel (260505 batch)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def empty_allowlist(tmp_path, monkeypatch):
    allowlist_path = tmp_path / "d-class-allowlist.json"
    allowlist_path.write_text("[]")
    monkeypatch.setenv("DCLASS_ALLOWLIST_PATH", str(allowlist_path))
    import importlib
    import app.api.d_class as d_class_module
    importlib.reload(d_class_module)
    yield allowlist_path


@pytest.fixture
def populated_allowlist(tmp_path, monkeypatch):
    allowlist_path = tmp_path / "d-class-allowlist.json"
    sha = "a" * 64
    allowlist_path.write_text(json.dumps([
        {
            "service_name": "tqsdk-login",
            "allowed_executable_sha256": sha,
            "allowed_secret_keys": ["secret.test.tqsdk.password"],
        }
    ]))
    monkeypatch.setenv("DCLASS_ALLOWLIST_PATH", str(allowlist_path))
    import importlib
    import app.api.d_class as d_class_module
    importlib.reload(d_class_module)
    yield allowlist_path, sha


def test_d_class_grant_denied_when_caller_not_in_allowlist(client, empty_allowlist):
    r = client.post(
        "/api/d-class/grant",
        json={
            "service_name": "any-service",
            "caller_executable_sha256": "f" * 64,
        },
    )
    assert r.status_code == 403
    detail = r.json().get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("code") == "D_CLASS_DENIED"


def test_d_class_grant_rejects_short_sha256(client, empty_allowlist):
    r = client.post(
        "/api/d-class/grant",
        json={
            "service_name": "x",
            "caller_executable_sha256": "tooshort",
        },
    )
    assert r.status_code == 422


def test_d_class_grant_rejects_empty_service_name(client, empty_allowlist):
    r = client.post(
        "/api/d-class/grant",
        json={
            "service_name": "",
            "caller_executable_sha256": "a" * 64,
        },
    )
    assert r.status_code == 422
