"""Security regression tests (SECU-03, SECU-04, SECU-05)."""

from __future__ import annotations

import re
from pathlib import Path

# OpenAI-style key shape — scan application source only (not tests).
_SK_PATTERN = re.compile(r"sk-[a-zA-Z0-9]{20,}")


def test_no_plaintext_in_source() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    app_dir = backend_root / "app"
    for py_file in app_dir.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        text = py_file.read_text(encoding="utf-8")
        match = _SK_PATTERN.search(text)
        assert match is None, f"disallowed sk-* pattern in {py_file}"


def test_no_plaintext_in_workspace() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    policy = repo_root / "docs" / "AGENT_WORKSPACE.md"
    assert policy.is_file(), f"missing {policy}"
    body = policy.read_text(encoding="utf-8")
    assert (
        "Secret plaintext MUST NOT appear in repository files intended for AI agents."
        in body
    )
    assert "Programs MUST use binding references" in body


def test_vault_body_models_hide_passwords_in_repr() -> None:
    """SecretStr fields must not leak passwords in repr or str."""
    from app.api.vault_routes import ChangePasswordBody, VaultUnlockBody

    unlock = VaultUnlockBody(master_password="my-master-secret")
    assert "my-master-secret" not in repr(unlock)
    assert "my-master-secret" not in str(unlock)

    change = ChangePasswordBody(current_password="old-pass-val", new_password="new-pass-val-long")
    assert "old-pass-val" not in repr(change)
    assert "new-pass-val-long" not in repr(change)


def test_localhost_binding() -> None:
    from app.core.config import Settings

    assert Settings().api_host == "127.0.0.1"
    backend_root = Path(__file__).resolve().parents[1]
    root = backend_root / "app"
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        text = p.read_text(encoding="utf-8")
        assert "0.0.0.0" not in text, f"forbidden bind in {p}"
