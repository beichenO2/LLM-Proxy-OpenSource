"""Cursor Agent CLI models exposed through PolarPrivate.

Each caller-facing model id maps to one CLI ``--model`` slug. Multiple ids may
share the same slug (e.g. ``C000`` and ``composer-2.5-fast`` → Composer 2.5 Fast).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CURSOR_SERVICE_NAME = "llm.local.cursor"

# caller model id → Cursor CLI --model slug
CURSOR_CALLER_MODELS: dict[str, str] = {
    "C000": "composer-2.5-fast",
    "composer-2.5-fast": "composer-2.5-fast",
}

CURSOR_MODEL_DESCRIPTIONS: dict[str, str] = {
    "C000": "Composer 2.5 Fast (opaque code; same backend as composer-2.5-fast).",
    "composer-2.5-fast": "Composer 2.5 Fast via Cursor CLI (agent login required).",
}


def _default_agent_bin() -> Path:
    return Path.home() / ".local" / "bin" / "agent"


def agent_bin() -> str:
    """Resolve Cursor CLI executable to an absolute path."""
    env_bin = (os.environ.get("CURSOR_AGENT_BIN") or "").strip()
    if env_bin:
        return str(Path(env_bin).expanduser())

    found = shutil.which("agent")
    if found:
        return found

    home_bin = _default_agent_bin()
    if home_bin.is_file():
        return str(home_bin)

    return "agent"


def cursor_workspace() -> str:
    ws = Path(
        os.environ.get("CURSOR_AGENT_WORKSPACE", "/tmp/cursor-agent-smoke")
    ).expanduser()
    ws.mkdir(parents=True, exist_ok=True)
    return str(ws)


def agent_timeout_seconds() -> float:
    raw = os.environ.get("CURSOR_AGENT_TIMEOUT", "180")
    try:
        return max(30.0, float(raw))
    except ValueError:
        return 600.0


def resolve_cursor_caller(model: str) -> str | None:
    """Return canonical caller model id, or None if unknown."""
    raw = (model or "").strip()
    if not raw:
        return None
    if raw.upper() == "C000":
        return "C000"
    lower = raw.lower()
    if lower in CURSOR_CALLER_MODELS:
        return lower
    return None


def is_cursor_caller_model(model: str) -> bool:
    return resolve_cursor_caller(model) is not None


def resolve_cursor_cli_slug(caller_model: str) -> str:
    caller = resolve_cursor_caller(caller_model)
    if not caller:
        raise ValueError(
            f"invalid Cursor model: {caller_model!r} "
            f"(use C000 or composer-2.5-fast)"
        )
    env_key = f"CURSOR_MODEL_{caller.upper().replace('.', '_').replace('-', '_')}"
    return (
        os.environ.get(env_key)
        or os.environ.get("CURSOR_MODEL")
        or CURSOR_CALLER_MODELS[caller]
    )


def all_cursor_caller_models() -> list[str]:
    return sorted(CURSOR_CALLER_MODELS.keys())


def cursor_cli_available() -> bool:
    path = Path(agent_bin()).expanduser()
    return path.is_file() and os.access(path, os.X_OK)


def _read_macos_http_proxy() -> str | None:
    """Return http://127.0.0.1:PORT when macOS system HTTP proxy is enabled."""
    if sys.platform != "darwin":
        return None
    try:
        proc = subprocess.run(
            ["scutil", "--proxy"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or "HTTPEnable : 1" not in proc.stdout:
        return None
    host_match = re.search(r"HTTPProxy\s*:\s*(\S+)", proc.stdout)
    port_match = re.search(r"HTTPPort\s*:\s*(\d+)", proc.stdout)
    if not host_match or not port_match:
        return None
    return f"http://{host_match.group(1)}:{port_match.group(1)}"


def agent_subprocess_env() -> dict[str, str]:
    """Environment for Cursor CLI subprocess (Node does not use macOS proxy by default)."""
    env = os.environ.copy()
    explicit = (os.environ.get("CURSOR_AGENT_HTTP_PROXY") or "").strip()
    if explicit:
        env["HTTP_PROXY"] = explicit
        env["HTTPS_PROXY"] = (os.environ.get("CURSOR_AGENT_HTTPS_PROXY") or explicit).strip()
        return env
    if env.get("HTTP_PROXY") or env.get("HTTPS_PROXY"):
        return env
    mac_proxy = _read_macos_http_proxy()
    if mac_proxy:
        env["HTTP_PROXY"] = mac_proxy
        env["HTTPS_PROXY"] = mac_proxy
    return env
