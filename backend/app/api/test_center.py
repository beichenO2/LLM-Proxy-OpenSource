"""Test Center API: LLM connectivity testing and service status (R11)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_unlocked_vault
from app.core.model_routing import get_all_registered_services
from app.db.models import Binding, BindingSecret, LLMServiceStatus, Secret
from app.logging_config import sanitize_user_facing_string
from app.services.sign_providers import PROVIDERS
from app.services.vault import VaultService

router = APIRouter(prefix="/test-center", tags=["test-center"])


# D-class allowlist path (same as d_class.py)
DCLASS_ALLOWLIST_PATH = Path(os.environ.get(
    "DCLASS_ALLOWLIST_PATH",
    os.path.expanduser("~/.privportal/d-class-allowlist.json"),
))


def _sanitize(msg: str) -> str:
    """User-visible test messages: no raw secrets or sk-* key material (TEST-05)."""
    return sanitize_user_facing_string(msg)


class TestCenterRunBody(BaseModel):
    test_type: Literal["llm_connectivity", "sign_providers", "d_class", "all"] = Field(default="all")


class TestResultItem(BaseModel):
    name: str
    status: Literal["pass", "fail", "skip"]
    message: str
    duration_ms: int


class TestCenterRunResponse(BaseModel):
    results: list[TestResultItem]


class LLMServiceStatusOut(BaseModel):
    """LLM service status for dashboard display (R11)."""
    service_name: str
    last_call_at: str | None
    last_call_status: str | None
    last_call_error: str | None
    last_call_latency_ms: int | None
    last_success_at: str | None
    consecutive_failures: int


class LLMStatusResponse(BaseModel):
    """Response for LLM status query."""
    services: list[LLMServiceStatusOut]


def _update_service_status(
    session: Session,
    service_name: str,
    is_error: bool = False,
    error_message: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Update LLMServiceStatus after connectivity test.

    Records the result of the connectivity test to enable status dashboards.
    """
    if not service_name.startswith("llm."):
        return

    status_row = session.query(LLMServiceStatus).filter(
        LLMServiceStatus.service_name == service_name
    ).first()

    now = datetime.now(timezone.utc)
    status = "error" if is_error else "success"

    if status_row is None:
        status_row = LLMServiceStatus(
            service_name=service_name,
            last_call_at=now,
            last_call_status=status,
            last_call_error=error_message,
            last_call_latency_ms=latency_ms,
            last_success_at=now if not is_error else None,
            consecutive_failures=1 if is_error else 0,
        )
        session.add(status_row)
    else:
        status_row.last_call_at = now
        status_row.last_call_status = status
        status_row.last_call_error = error_message
        status_row.last_call_latency_ms = latency_ms
        if not is_error:
            status_row.last_success_at = now
            status_row.consecutive_failures = 0
        else:
            status_row.consecutive_failures += 1

    try:
        session.commit()
    except Exception:
        session.rollback()


@router.post("/run", response_model=TestCenterRunResponse)
async def run_tests(
    body: TestCenterRunBody,
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> TestCenterRunResponse:
    """Run connectivity tests for various service types.

    Tests that each registered service has a valid binding and secret configured.
    Updates LLMServiceStatus with test results.
    
    test_type options:
    - llm_connectivity: Test LLM services only
    - sign_providers: Test sign providers (weex, feishu-webhook, aliyun-sigv1)
    - d_class: Test D-class services (tqsdk-login etc.)
    - all: Run all tests
    """
    results: list[TestResultItem] = []
    
    if body.test_type in ("llm_connectivity", "all"):
        results.extend((await _run_llm_connectivity(session)).results)
    
    if body.test_type in ("sign_providers", "all"):
        results.extend((await _run_sign_provider_tests(session)).results)
    
    if body.test_type in ("d_class", "all"):
        results.extend((await _run_d_class_tests(session)).results)
    
    if not results:
        results.append(TestResultItem(
            name="no_tests",
            status="skip",
            message=_sanitize("No tests were run"),
            duration_ms=0,
        ))
    
    return TestCenterRunResponse(results=results)


@router.get("/llm-status", response_model=LLMStatusResponse)
async def get_llm_status(
    session: Annotated[Session, Depends(get_db)],
    _vault: Annotated[VaultService, Depends(require_unlocked_vault)],
) -> LLMStatusResponse:
    """Get status for all registered LLM services (R11).

    Returns the last call status for each service registered in model_routing.
    """
    registered_services = get_all_registered_services()

    status_rows = session.scalars(
        select(LLMServiceStatus).where(LLMServiceStatus.service_name.in_(registered_services))
    ).all()
    status_by_name = {s.service_name: s for s in status_rows}

    services: list[LLMServiceStatusOut] = []
    for svc_name in sorted(registered_services):
        status = status_by_name.get(svc_name)
        if status:
            services.append(LLMServiceStatusOut(
                service_name=status.service_name,
                last_call_at=status.last_call_at.isoformat() if status.last_call_at else None,
                last_call_status=status.last_call_status,
                last_call_error=status.last_call_error,
                last_call_latency_ms=status.last_call_latency_ms,
                last_success_at=status.last_success_at.isoformat() if status.last_success_at else None,
                consecutive_failures=status.consecutive_failures,
            ))
        else:
            services.append(LLMServiceStatusOut(
                service_name=svc_name,
                last_call_at=None,
                last_call_status=None,
                last_call_error="Never called",
                last_call_latency_ms=None,
                last_success_at=None,
                consecutive_failures=0,
            ))

    return LLMStatusResponse(services=services)


async def _run_llm_connectivity(session: Session) -> TestCenterRunResponse:
    """Test LLM service connectivity by verifying bindings and secrets.

    This test verifies that each registered LLM service has a valid binding
    and secret configured. Updates LLMServiceStatus with test results.
    """
    registered_services = get_all_registered_services()
    results: list[TestResultItem] = []

    for svc_name in sorted(registered_services):
        t0 = time.perf_counter()

        binding = session.scalars(
            select(Binding).where(Binding.service_name == svc_name, Binding.project_id.is_(None))
        ).first()

        if binding is None:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            results.append(TestResultItem(
                name=f"llm:{svc_name}",
                status="fail",
                message=_sanitize(f"Binding not configured for {svc_name}"),
                duration_ms=latency_ms,
            ))
            _update_service_status(session, svc_name, is_error=True, error_message="Binding not configured", latency_ms=latency_ms)
            continue

        secret = session.scalars(
            select(Secret).where(Secret.key == binding.secret_ref_key, Secret.project_id.is_(None))
        ).first()

        if secret is None:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            results.append(TestResultItem(
                name=f"llm:{svc_name}",
                status="fail",
                message=_sanitize(f"Secret '{binding.secret_ref_key}' not found"),
                duration_ms=latency_ms,
            ))
            _update_service_status(session, svc_name, is_error=True, error_message=f"Secret '{binding.secret_ref_key}' not found", latency_ms=latency_ms)
            continue

        if not secret.enabled:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            results.append(TestResultItem(
                name=f"llm:{svc_name}",
                status="fail",
                message=_sanitize(f"Secret '{binding.secret_ref_key}' is disabled"),
                duration_ms=latency_ms,
            ))
            _update_service_status(session, svc_name, is_error=True, error_message=f"Secret '{binding.secret_ref_key}' is disabled", latency_ms=latency_ms)
            continue

        if not secret.base_url:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            results.append(TestResultItem(
                name=f"llm:{svc_name}",
                status="fail",
                message=_sanitize(f"Secret '{binding.secret_ref_key}' has no base_url"),
                duration_ms=latency_ms,
            ))
            _update_service_status(session, svc_name, is_error=True, error_message=f"Secret '{binding.secret_ref_key}' has no base_url", latency_ms=latency_ms)
            continue

        latency_ms = int((time.perf_counter() - t0) * 1000)
        results.append(TestResultItem(
            name=f"llm:{svc_name}",
            status="pass",
            message=_sanitize(f"Binding and secret configured for {svc_name}"),
            duration_ms=latency_ms,
        ))
        _update_service_status(session, svc_name, is_error=False, latency_ms=latency_ms)

    if not results:
        results.append(TestResultItem(
            name="llm_connectivity",
            status="skip",
            message=_sanitize("No LLM services registered"),
            duration_ms=0,
        ))

    return TestCenterRunResponse(results=results)


async def _run_sign_provider_tests(session: Session) -> TestCenterRunResponse:
    """Test sign provider connectivity by verifying bindings and required secrets.

    Sign providers (weex, feishu-webhook, aliyun-sigv1) require specific secret keys
    to be configured. This test verifies that each provider has at least one binding
    with all required secrets configured through the BindingSecret association table.
    """
    results: list[TestResultItem] = []

    for provider_name in sorted(PROVIDERS.keys()):
        t0 = time.perf_counter()
        provider_class = PROVIDERS[provider_name]
        provider_instance = provider_class()
        required_keys = provider_instance.required_secret_keys()

        # Find bindings that are configured for this sign provider
        # Sign provider bindings have a key field like "binding.weex" or "weex.main"
        bindings_for_provider = session.scalars(
            select(Binding).where(
                Binding.key.like(f"%{provider_name}%"),
                Binding.project_id.is_(None)
            )
        ).all()

        if not bindings_for_provider:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            results.append(TestResultItem(
                name=f"sign:{provider_name}",
                status="skip",
                message=_sanitize(f"No binding configured for {provider_name} (requires: {', '.join(required_keys)})"),
                duration_ms=latency_ms,
            ))
            continue

        # Check each binding for completeness
        best_binding_status = "fail"
        best_binding_message = ""
        for binding in bindings_for_provider:
            # Get secrets associated with this binding through BindingSecret
            binding_secrets = session.scalars(
                select(BindingSecret).where(BindingSecret.binding_id == binding.id)
            ).all()

            # Build a map of field_name -> secret
            secrets_map: dict[str, Secret] = {}
            for assoc in binding_secrets:
                secret = session.get(Secret, assoc.secret_id)
                if secret:
                    field_name = secret.key.split(".")[-1]
                    if field_name in required_keys:
                        secrets_map[field_name] = secret

            # Check if all required keys are present and enabled
            missing_keys = [k for k in required_keys if k not in secrets_map]
            disabled_keys = [k for k in required_keys if k in secrets_map and not secrets_map[k].enabled]

            if not missing_keys and not disabled_keys:
                # This binding is complete and valid
                best_binding_status = "pass"
                best_binding_message = f"Sign provider {provider_name} configured via binding '{binding.key}' (requires: {', '.join(required_keys)})"
                break  # Found a valid binding, no need to check others
            elif not missing_keys and disabled_keys:
                # Has all keys but some are disabled
                if best_binding_status == "fail":
                    best_binding_message = f"Binding '{binding.key}' has disabled secrets: {', '.join(disabled_keys)}"
            else:
                # Missing some keys
                if best_binding_status == "fail":
                    best_binding_message = f"Binding '{binding.key}' missing required secrets: {', '.join(missing_keys)}"

        latency_ms = int((time.perf_counter() - t0) * 1000)
        results.append(TestResultItem(
            name=f"sign:{provider_name}",
            status=best_binding_status,
            message=_sanitize(best_binding_message),
            duration_ms=latency_ms,
        ))

    if not results:
        results.append(TestResultItem(
            name="sign_providers",
            status="skip",
            message=_sanitize("No sign providers registered"),
            duration_ms=0,
        ))

    return TestCenterRunResponse(results=results)


def _load_dclass_allowlist() -> list[dict]:
    """Load D-class allowlist from file."""
    if not DCLASS_ALLOWLIST_PATH.exists():
        return []
    try:
        data = json.loads(DCLASS_ALLOWLIST_PATH.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


async def _run_d_class_tests(session: Session) -> TestCenterRunResponse:
    """Test D-class service connectivity by verifying allowlist and secrets.

    D-class services (like tqsdk-login) are configured in the allowlist file.
    This test verifies that each allowlisted service has the required secrets
    configured in the database.
    """
    results: list[TestResultItem] = []
    allowlist = _load_dclass_allowlist()

    if not allowlist:
        results.append(TestResultItem(
            name="d_class:allowlist",
            status="skip",
            message=_sanitize(f"D-class allowlist not found or empty at {DCLASS_ALLOWLIST_PATH}"),
            duration_ms=0,
        ))
        return TestCenterRunResponse(results=results)

    for entry in allowlist:
        service_name = entry.get("service_name", "unknown")
        allowed_keys = entry.get("allowed_secret_keys", [])
        
        t0 = time.perf_counter()

        if not allowed_keys:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            results.append(TestResultItem(
                name=f"d_class:{service_name}",
                status="fail",
                message=_sanitize(f"Allowlist entry for {service_name} has no secret keys configured"),
                duration_ms=latency_ms,
            ))
            continue

        # Check each required secret
        missing_keys = []
        disabled_keys = []
        for key in allowed_keys:
            secret = session.scalars(
                select(Secret).where(Secret.key == key, Secret.project_id.is_(None))
            ).first()
            if secret is None:
                missing_keys.append(key)
            elif not secret.enabled:
                disabled_keys.append(key)

        latency_ms = int((time.perf_counter() - t0) * 1000)

        if missing_keys:
            results.append(TestResultItem(
                name=f"d_class:{service_name}",
                status="fail",
                message=_sanitize(f"Missing secrets: {', '.join(missing_keys)}"),
                duration_ms=latency_ms,
            ))
        elif disabled_keys:
            results.append(TestResultItem(
                name=f"d_class:{service_name}",
                status="fail",
                message=_sanitize(f"Disabled secrets: {', '.join(disabled_keys)}"),
                duration_ms=latency_ms,
            ))
        else:
            results.append(TestResultItem(
                name=f"d_class:{service_name}",
                status="pass",
                message=_sanitize(f"D-class service {service_name} configured ({len(allowed_keys)} secrets)"),
                duration_ms=latency_ms,
            ))

    return TestCenterRunResponse(results=results)
