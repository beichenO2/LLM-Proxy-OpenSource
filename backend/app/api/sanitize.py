"""Sanitize mappings API — exports secret key-value pairs for SDK consumption.

Also provides PII pattern detection endpoints for scanning arbitrary text.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_authenticated_session
from app.db.models import CustomPiiPattern, Secret
from app.services.pii_scanner import PiiMatch as _PiiMatch
from app.services.pii_scanner import (
    add_custom_pattern,
    get_custom_patterns,
    get_patterns,
    redact_text,
    remove_custom_pattern,
    scan_text,
)
from app.services.vault import VaultService

router = APIRouter(prefix="/sanitize", tags=["sanitize"])


class SecretMapping(BaseModel):
    key: str
    project_id: str | None


class MappingsResponse(BaseModel):
    secrets: list[SecretMapping]
    version: str


@router.get("/mappings")
def get_mappings(
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_authenticated_session)],
    project_id: str | None = Query(default=None, description="Filter by project ID"),
) -> MappingsResponse:
    """Export secret mappings for SDK-based sanitization.

    SECURITY: requires a valid browser session cookie (unconditional).
    Secret keys are returned WITHOUT values.
    """
    sec_stmt = select(Secret).where(Secret.enabled.is_(True))

    if project_id is not None:
        sec_stmt = sec_stmt.where(Secret.project_id == project_id)

    secrets = session.scalars(sec_stmt).all()

    return MappingsResponse(
        secrets=[
            SecretMapping(key=s.key, project_id=s.project_id)
            for s in secrets
        ],
        version="2",
    )


# ── PII pattern detection ────────────────────────────────────────────


class PiiMatchOut(BaseModel):
    label: str
    description: str
    start: int
    end: int
    text: str


class ScanRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500_000)


class ScanResponse(BaseModel):
    has_pii: bool
    count: int
    matches: list[PiiMatchOut]


class RedactRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500_000)
    placeholder: str = "[[{label}]]"


class RedactResponse(BaseModel):
    has_pii: bool
    count: int
    redacted: str
    matches: list[PiiMatchOut]


class PatternInfo(BaseModel):
    label: str
    description: str
    pattern: str


@router.post("/scan")
def scan_for_pii(body: ScanRequest) -> ScanResponse:
    """Scan text for PII patterns (email, phone, ID card, API keys, etc.).

    Does not require vault unlock — patterns are static regexes.
    """
    result = scan_text(body.text)
    return ScanResponse(
        has_pii=result.has_pii,
        count=len(result.matches),
        matches=[
            PiiMatchOut(
                label=m.label,
                description=m.description,
                start=m.start,
                end=m.end,
                text=m.text,
            )
            for m in result.matches
        ],
    )


@router.post("/redact")
def redact_pii(body: RedactRequest) -> RedactResponse:
    """Scan text and replace detected PII with placeholder tokens."""
    redacted, result = redact_text(body.text, placeholder=body.placeholder)
    return RedactResponse(
        has_pii=result.has_pii,
        count=len(result.matches),
        redacted=redacted,
        matches=[
            PiiMatchOut(
                label=m.label,
                description=m.description,
                start=m.start,
                end=m.end,
                text=m.text,
            )
            for m in result.matches
        ],
    )


@router.get("/patterns")
def list_patterns() -> list[PatternInfo]:
    """List all registered PII detection patterns."""
    return [PatternInfo(**p) for p in get_patterns()]


# ── Batch sanitize ───────────────────────────────────────────────────


class BatchItem(BaseModel):
    id: str = Field(description="Client-side identifier for matching results")
    text: str = Field(min_length=1, max_length=500_000)


class BatchRedactRequest(BaseModel):
    items: list[BatchItem] = Field(min_length=1, max_length=100)
    placeholder: str = "[[{label}]]"


class BatchRedactResultItem(BaseModel):
    id: str
    has_pii: bool
    count: int
    redacted: str


class BatchRedactResponse(BaseModel):
    total_items: int
    total_pii_found: int
    results: list[BatchRedactResultItem]


@router.post("/redact/batch")
def batch_redact_pii(body: BatchRedactRequest) -> BatchRedactResponse:
    """Scan and redact PII from multiple text items in a single request."""
    results: list[BatchRedactResultItem] = []
    total_pii = 0
    for item in body.items:
        redacted, scan_result = redact_text(item.text, placeholder=body.placeholder)
        count = len(scan_result.matches)
        total_pii += count
        results.append(BatchRedactResultItem(
            id=item.id,
            has_pii=scan_result.has_pii,
            count=count,
            redacted=redacted,
        ))
    return BatchRedactResponse(
        total_items=len(results),
        total_pii_found=total_pii,
        results=results,
    )


# ── Custom PII patterns ─────────────────────────────────────────────


class CustomPatternRequest(BaseModel):
    label: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=200)
    pattern: str = Field(min_length=1, max_length=500)


@router.post("/patterns/custom", status_code=201)
def create_custom_pattern(
    body: CustomPatternRequest,
    session: Annotated[Session, Depends(get_db)],
) -> PatternInfo:
    """Register a user-defined PII detection pattern (persisted to DB)."""
    import re
    try:
        re.compile(body.pattern)
    except re.error as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=f"Invalid regex: {e}")
    add_custom_pattern(body.label, body.description, body.pattern)
    existing = session.query(CustomPiiPattern).filter(CustomPiiPattern.label == body.label).first()
    if existing:
        existing.description = body.description
        existing.pattern = body.pattern
    else:
        session.add(CustomPiiPattern(label=body.label, description=body.description, pattern=body.pattern))
    return PatternInfo(label=body.label, description=body.description, pattern=body.pattern)


@router.delete("/patterns/custom/{label}")
def delete_custom_pattern(
    label: str,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Remove a user-defined PII detection pattern by label (from memory and DB)."""
    if not remove_custom_pattern(label):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Custom pattern '{label}' not found")
    session.query(CustomPiiPattern).filter(CustomPiiPattern.label == label).delete()
    return {"status": "deleted", "label": label}


@router.get("/patterns/custom")
def list_custom_patterns() -> list[PatternInfo]:
    """List only user-defined custom PII patterns."""
    return [PatternInfo(**p) for p in get_custom_patterns()]
