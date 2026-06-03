"""Per-browser session management for vault access.

Sessions are persisted in the database so they survive server restarts.
Each session carries its own role/user_id, enabling per-browser identity.
API callers (no Origin header) bypass the cookie requirement.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db.models import BrowserSession

COOKIE_NAME = "pp_session"
COOKIE_MAX_AGE = 365 * 24 * 3600  # 1 year


def _utcnow() -> datetime:
    """Return a naive UTC datetime (SQLite doesn't preserve tzinfo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: Session,
    *,
    role: str = "admin",
    username: str = "admin",
    user_id: str | None = None,
) -> str:
    """Generate a new session token, persist it, and return the raw token."""
    token = secrets.token_urlsafe(48)
    now = _utcnow()
    row = BrowserSession(
        id=str(uuid.uuid4()),
        token_hash=_hash_token(token),
        user_id=user_id,
        role=role,
        username=username,
        expires_at=now + timedelta(seconds=COOKIE_MAX_AGE),
        created_at=now,
        last_seen_at=now,
    )
    db.add(row)
    db.flush()
    return token


def validate_session(db: Session, token: str | None) -> BrowserSession | None:
    """Return the session row if valid and not expired, else None.

    Also bumps last_seen_at for active sessions (at most once per minute
    to avoid excessive writes).
    """
    if not token:
        return None
    h = _hash_token(token)
    now = _utcnow()
    row = db.scalar(
        select(BrowserSession).where(
            BrowserSession.token_hash == h,
            BrowserSession.expires_at > now,
        )
    )
    if row is None:
        return None
    if (now - row.last_seen_at).total_seconds() > 60:
        row.last_seen_at = now
        db.flush()
    return row


def revoke_all_sessions(db: Session) -> int:
    """Delete all sessions (e.g. on vault lock or password change). Returns count deleted."""
    result = db.execute(delete(BrowserSession))
    db.flush()
    return result.rowcount  # type: ignore[return-value]


def revoke_session(db: Session, token: str) -> bool:
    """Delete a single session by raw token. Returns True if found."""
    h = _hash_token(token)
    result = db.execute(
        delete(BrowserSession).where(BrowserSession.token_hash == h)
    )
    db.flush()
    return (result.rowcount or 0) > 0


def cleanup_expired(db: Session) -> int:
    """Remove expired sessions. Call periodically."""
    now = _utcnow()
    result = db.execute(
        delete(BrowserSession).where(BrowserSession.expires_at <= now)
    )
    db.flush()
    return result.rowcount  # type: ignore[return-value]
