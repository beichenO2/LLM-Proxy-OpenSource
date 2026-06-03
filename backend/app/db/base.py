"""SQLAlchemy declarative base for PrivPortal ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all database models."""
