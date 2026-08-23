"""A retrievable span of one memory, with its embedding."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from memora.config import get_settings
from memora.db.base import Base

EMBEDDING_DIMS = get_settings().embedding_dims


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # 1-based source page for PDFs, NULL for images and plain text. Populated at
    # extraction so the viewer can open on the match rather than on page one.
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When the content is about, not when it was ingested. A date filter needs a
    # column; as text it is only a semantic match against the words.
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Per-format extras - location, participants, recurrence - that nothing filters
    # on yet. Promoted to columns when something does.
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Title + nearest heading, prepended before embedding so an isolated chunk still
    # carries where it came from. Stored separately so the cited text stays clean.
    contextual_prefix: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMS), nullable=False)
