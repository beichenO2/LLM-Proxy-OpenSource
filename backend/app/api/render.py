"""Template render API with vault-backed identity decryption."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_authenticated_session
from app.services.export_format import markdown_to_html_fragment, wrap_html_document
from app.services.template_render import render_template
from app.services.vault import VaultService

router = APIRouter(prefix="/render", tags=["render"])


class RenderRequest(BaseModel):
    template: str = Field(min_length=1)
    project_id: str | None = None


class RenderResponse(BaseModel):
    rendered: str
    warnings: list[dict[str, Any]]
    stats: dict[str, int]


@router.post("")
def post_render(
    body: RenderRequest,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_authenticated_session)],
) -> RenderResponse:
    """Render a template by substituting ``[[placeholder]]`` markers with identity values."""
    result = render_template(
        session, body.template, body.project_id,
        decrypt=vault.decrypt_secret_value,
    )
    return RenderResponse(
        rendered=result.rendered,
        warnings=result.warnings,
        stats=result.stats,
    )


class PreviewResponse(BaseModel):
    html: str
    warnings: list[dict[str, Any]]
    stats: dict[str, int]


@router.post("/preview")
def post_render_preview(
    body: RenderRequest,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_authenticated_session)],
) -> PreviewResponse:
    """Render a template and return an HTML preview (without file download)."""
    result = render_template(
        session, body.template, body.project_id,
        decrypt=vault.decrypt_secret_value,
    )
    html_fragment = markdown_to_html_fragment(result.rendered)
    html_doc = wrap_html_document(html_fragment)
    return PreviewResponse(
        html=html_doc,
        warnings=result.warnings,
        stats=result.stats,
    )
