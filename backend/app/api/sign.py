"""HMAC/Signature signing endpoints — B-class "use key" interface.

Secret material never leaves the PolarPrivate process boundary.
Callers receive only the computed signature headers.
No authentication required (any localhost caller can use).
"""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_unlocked_vault
from app.db.models import Binding, BindingSecret, Secret
from app.services.sign_providers import PROVIDERS
from app.services.vault import VaultService

router = APIRouter(prefix="/sign", tags=["sign"])


class SignRequest(BaseModel):
    binding: str
    method: str = "GET"
    path: str = "/"
    query: str = ""
    body: str = ""
    timestamp: str | None = None


@router.post("/{provider}/{action}")
def sign_request(
    provider: str,
    action: str,
    body: SignRequest,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> dict[str, Any]:
    """Sign a request using the specified provider.

    The binding field identifies which secret triple (api_key/api_secret/passphrase etc.)
    to use. Secret material is decrypted, used for signing, then discarded—never returned.
    """
    if provider not in PROVIDERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider}. Available: {', '.join(PROVIDERS)}",
        )

    # Look up binding by key field (for sign providers)
    binding_row = session.scalars(select(Binding).where(Binding.key == body.binding)).first()
    if binding_row is None:
        raise HTTPException(status_code=404, detail=f"Binding not found: {body.binding}")

    provider_instance = PROVIDERS[provider]()
    required = provider_instance.required_secret_keys()

    secrets_data: dict[str, str] = {}
    # binding_row.secrets is a list of BindingSecret association objects
    for assoc in binding_row.secrets:
        secret_row = session.get(Secret, assoc.secret_id)
        if secret_row is None or not secret_row.enabled:
            continue
        # Extract field name from secret key (e.g., "secret.weex.api_key" -> "api_key")
        field_name = secret_row.key.split(".")[-1]
        if field_name in required:
            secrets_data[field_name] = vault.decrypt_secret_value(secret_row.value)

    missing = [k for k in required if k not in secrets_data]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Binding {body.binding} missing required secret keys: {missing}",
        )

    timestamp = body.timestamp or str(int(time.time()))

    try:
        headers = provider_instance.sign(
            secrets=secrets_data,
            method=body.method,
            path=body.path,
            query=body.query,
            body=body.body,
            timestamp=timestamp,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Signing failed: {e}",
        ) from None

    return {"headers": headers, "provider": provider, "action": action}
