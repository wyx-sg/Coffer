"""Shared SQLAlchemy metadata for every kind's ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All ORM models inherit from this so Alembic finds them in one metadata."""
