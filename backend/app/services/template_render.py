"""Regex-based template rendering for [[binding.*]], [[secret_ref.*]]."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Binding

PLACEHOLDER_RE = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass
class RenderResult:
    """Output of render_template: substituted text, warnings, and resolution counters."""

    rendered: str
    warnings: list[dict[str, Any]] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def _empty_stats() -> dict[str, int]:
    return {
        "resolved_binding": 0,
        "unresolved_binding": 0,
        "secret_ref_rendered": 0,
        "malformed": 0,
    }


def _binding_project_clause(project_id: str | None):
    if project_id is None:
        return Binding.project_id.is_(None)
    return Binding.project_id == project_id


def render_template(
    session: Session,
    template: str,
    project_id: str | None = None,
    *,
    decrypt: Any = None,  # deprecated, kept for API compatibility
) -> RenderResult:
    """
    Replace [[binding.*]] and [[secret_ref.*]] placeholders.

    Binding and secret_ref render as [secret_ref:...] tags.
    """
    warnings: list[dict[str, Any]] = []
    stats = _empty_stats()

    binding_rows = session.scalars(
        select(Binding).where(_binding_project_clause(project_id))
    ).all()
    bindings_by_name: dict[str, Binding] = {r.service_name: r for r in binding_rows}

    def repl(m: re.Match[str]) -> str:
        raw_inner = m.group(1)
        allowed_prefixes = ("binding", "secret_ref")

        if "." not in raw_inner:
            stats["malformed"] += 1
            warnings.append({"code": "MALFORMED_PLACEHOLDER", "raw": raw_inner})
            return m.group(0)

        type_part, rest = raw_inner.split(".", 1)
        if type_part not in allowed_prefixes:
            stats["malformed"] += 1
            warnings.append({"code": "MALFORMED_PLACEHOLDER", "raw": raw_inner})
            return m.group(0)

        if type_part == "binding":
            brow = bindings_by_name.get(rest)
            if brow is not None:
                stats["resolved_binding"] += 1
                return f"[secret_ref:{brow.secret_ref_key}]"
            stats["unresolved_binding"] += 1
            warnings.append({"code": "NOT_FOUND", "kind": "binding", "key": rest})
            return f"[ERROR:binding.{rest} not found]"

        # secret_ref
        stats["secret_ref_rendered"] += 1
        return f"[secret_ref:{rest}]"

    rendered = PLACEHOLDER_RE.sub(repl, template)
    return RenderResult(rendered=rendered, warnings=warnings, stats=stats)
