"""blob references on memories, page on chunks

The blob address is a hash, not a path. Nothing here stores a filesystem location - the
path is derived from blob_root + user_id + content_hash, so no row holds something a
later code path could join.

The uniqueness constraint is on (user_id, content_hash), not on content_hash alone. That
is what makes cross-user deduplication impossible to express: two users holding
byte-identical files get two rows and two blobs. A shared blob would let user B learn
that user A holds a file, purely from observing their own upload deduplicate.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "memories", sa.Column("byte_size", sa.Integer, nullable=False, server_default="0")
    )
    op.add_column(
        "memories",
        sa.Column("mime_type", sa.String(128), nullable=False, server_default=""),
    )
    op.add_column(
        "memories",
        sa.Column(
            "has_thumbnail", sa.Boolean, nullable=False, server_default=sa.false()
        ),
    )

    # Per-owner uniqueness. Partial, so rows predating blob storage (empty hash) do not
    # collide with each other.
    op.execute(
        "CREATE UNIQUE INDEX uq_memories_owner_content "
        "ON memories (user_id, content_hash) WHERE content_hash <> ''"
    )

    op.add_column("chunks", sa.Column("page", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "page")
    op.execute("DROP INDEX IF EXISTS uq_memories_owner_content")
    op.drop_column("memories", "has_thumbnail")
    op.drop_column("memories", "mime_type")
    op.drop_column("memories", "byte_size")
    op.drop_column("memories", "content_hash")
