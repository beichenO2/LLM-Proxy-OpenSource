"""File-style export API: POST /api/export (D-49–D-52)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_authenticated_session
from app.services.export_format import (
    markdown_to_html_fragment,
    rendered_to_plain_text,
    wrap_html_document,
)
from app.services.template_render import render_template
from app.services.vault import VaultService

router = APIRouter(prefix="/export", tags=["export"])


class ExportRequest(BaseModel):
    template: str = Field(min_length=1)
    format: Literal["markdown", "html", "txt"]
    project_id: str | None = None


@router.post("")
def post_export(
    body: ExportRequest,
    session: Annotated[Session, Depends(get_db)],
    vault: Annotated[VaultService, Depends(require_authenticated_session)],
) -> Response:
    """Render a template and export as markdown, HTML, or plain text."""
    result = render_template(
        session, body.template, body.project_id,
        decrypt=vault.decrypt_secret_value,
    )
    if body.format == "markdown":
        payload = result.rendered.encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
    elif body.format == "html":
        inner = markdown_to_html_fragment(result.rendered)
        payload = wrap_html_document(inner).encode("utf-8")
        media_type = "text/html; charset=utf-8"
    else:
        payload = rendered_to_plain_text(result.rendered).encode("utf-8")
        media_type = "text/plain; charset=utf-8"
    return Response(content=payload, media_type=media_type)
