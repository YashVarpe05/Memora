"""Declarative base for all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All models inherit from this. Alembic autogenerate reads Base.metadata."""
