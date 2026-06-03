"""Smoke tests for database fixtures."""

from sqlalchemy.orm import Session


def test_db_session_fixture_yields_session(db_session: Session) -> None:
    assert db_session.bind is not None
