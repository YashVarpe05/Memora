"""One CLIP vector per image, in a space the text index does not share.

512 dimensions against the text index's 768, and a similarity around 0.28 here means what
0.65 means there. The two are never compared numerically anywhere - fusion is by rank
(RRF), which is indifferent to scale. See services/search.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from memora.db.base import Base

# CLIP ViT-B/32. Pinned: changing it invalidates every row in this table, which is why
# the model name is stored per row rather than assumed.
CLIP_DIMS = 512


class ImageEmbedding(Base):
    __tablename__ = "image_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    memory_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(CLIP_DIMS), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
