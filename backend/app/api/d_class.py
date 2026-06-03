"""D-class controlled channel — one-time plaintext grant for third-party SDKs.

This is the ONLY remaining path where plaintext secrets can leave PolarPrivate.
It is restricted to a narrow allowlist: each entry specifies the service,
the allowed caller executable SHA256, and the permitted secret keys.

Agent processes (Cursor, Codex, Claude Code) are explicitly excluded
from the allowlist.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_unlocked_vault
from app.services.audit import append_audit_log
from app.services.vault import VaultService
from app.db.models import Secret
from app.logging_config import get_logger

router = APIRouter(prefix="/d-class", tags=["d-class"])
_LOG = get_logger(__name__)

ALLOWLIST_PATH = Path(os.environ.get(
    "DCLASS_ALLOWLIST_PATH",
    os.path.expanduser("~/.privportal/d-class-allowlist.json"),
))


class GrantRequest(BaseModel):
    service_name: str = Field(min_length=1)
    caller_executable_sha256: str = Field(min_length=64, max_length=64)


class GrantResponse(BaseModel):
    secrets: dict[str, str]


def _load_allowlist() -> list[dict]:
    if not ALLOWLIST_PATH.exists():
        return []
    try:
        data = json.loads(ALLOWLIST_PATH.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _find_entry(allowlist: list[dict], service_name: str, sha256: str) -> dict | None:
    for entry in allowlist:
        if (
            entry.get("service_name") == service_name
            and entry.get("allowed_executable_sha256") == sha256
        ):
            return entry
    return None


@router.post("/grant")
def grant(
    body: GrantRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> GrantResponse:
    """Grant one-time plaintext secrets to an allowlisted caller."""
    client_ip = request.client.host if request.client else ""
    caller_pid = request.headers.get("X-Caller-PID", "unknown")

    allowlist = _load_allowlist()
    entry = _find_entry(allowlist, body.service_name, body.caller_executable_sha256)

    if entry is None:
        _LOG.warning(
            "d_class_denied",
            service=body.service_name,
            sha256=body.caller_executable_sha256[:16] + "...",
            ip=client_ip,
            pid=caller_pid,
        )
        append_audit_log(
            session,
            action="d_class.grant.denied",
            detail=(
                f"service={body.service_name} "
                f"sha256={body.caller_executable_sha256[:16]}... "
                f"ip={client_ip} pid={caller_pid}"
            ),
            project_id=None,
        )
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "Caller not in D-class allowlist",
                "code": "D_CLASS_DENIED",
            },
        )

    allowed_keys: list[str] = entry.get("allowed_secret_keys", [])
    if not allowed_keys:
        raise HTTPException(
            status_code=422,
            detail={"detail": "Allowlist entry has no secret keys configured", "code": "NO_KEYS"},
        )

    result: dict[str, str] = {}
    for key in allowed_keys:
        row = session.scalars(select(Secret).where(Secret.key == key)).first()
        if row is None or not row.enabled:
            continue
        result[key] = vault.decrypt_secret_value(row.value)

    append_audit_log(
        session,
        action="d_class.grant.approved",
        detail=(
            f"service={body.service_name} "
            f"sha256={body.caller_executable_sha256[:16]}... "
            f"keys={','.join(allowed_keys)} "
            f"ip={client_ip} pid={caller_pid}"
        ),
        project_id=None,
    )
    _LOG.info(
        "d_class_granted",
        service=body.service_name,
        keys_count=len(result),
        ip=client_ip,
        pid=caller_pid,
    )

    return GrantResponse(secrets=result)
