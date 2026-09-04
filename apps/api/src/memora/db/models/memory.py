"""One ingested source: a PDF, an email, a voice note."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from memora.db.base import Base


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Every user-owned table carries this, and RLS keys on it.
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)

    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    # Display metadata only. Never used to build a filesystem path.
    filename: Mapped[str] = mapped_column(String(512), nullable=False)

    # The blob address. There is deliberately no path column: the path is derived
    # from blob_root + user_id + content_hash, so no row holds a filesystem path.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    has_thumbnail: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # What kind of document this is - aadhaar, receipt, marksheet. Null is normal and
    # means "no recognised type". Refusal compares this against what stage 1 was asked
    # for; see services/document_type.py for why that is not a similarity threshold.
    document_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Named in the stage 1 filter contract, so it will be filtered on.
    sender: Mapped[str | None] = mapped_column(String(320), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Where the device scan found this file. Null for anything uploaded by hand.
    #
    # Not the content hash: the hash identifies BYTES, and this identifies a LOCATION.
    # Two copies of one photo share a hash, and deleting one must not mark the other gone.
    device_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Set when a full scan no longer finds the file on the device. The memory survives:
    # "I know I had it" is the problem this product exists to solve, so forgetting a
    # document because it was tidied away would be the system reproducing that failure.
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
