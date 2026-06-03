"""In-memory log buffer API (LOGS-01, D-106 query contract)."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.log_buffer import get_log_buffer

router = APIRouter(prefix="/logs", tags=["logs"])


class LogItemOut(BaseModel):
    timestamp: str
    level: str
    source: str
    message: str


class LogListResponse(BaseModel):
    items: list[LogItemOut]


def _level_matches(filter_level: str, entry_level: str) -> bool:
    a, b = filter_level.upper(), entry_level.upper()
    return a in b or b in a


@router.get("")
def get_logs(
    level: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> LogListResponse:
    """Return newest-first log lines from the redacted ring buffer."""
    rows = get_log_buffer().snapshot_newest_first()
    out: list[dict[str, str]] = []
    for row in rows:
        if level is not None and not _level_matches(level, row["level"]):
            continue
        if source is not None and source not in row["source"]:
            continue
        if q is not None and q.lower() not in row["message"].lower():
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return LogListResponse(items=[LogItemOut.model_validate(x) for x in out])
