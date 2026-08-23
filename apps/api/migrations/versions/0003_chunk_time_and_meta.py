"""occurred_at and meta on chunks, sender and occurred_at on memories

occurred_at is when the content is *about*, distinct from created_at, which is when it
was ingested. It is a column rather than text because "the fee receipt from last
semester" is a date filter - as text it becomes a semantic match against the words "last
semester", which is a different question and does not work.

sender is promoted to a column because PRODUCT.md's stage 1 filter contract names it, so
it will be filtered on. Location, participants and recurrence rules will not be, and live
in meta until something needs them indexed.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chunks", sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "chunks",
        sa.Column(
            "meta",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ix_chunks_occurred_at", "chunks", ["user_id", "occurred_at"])

    op.add_column("memories", sa.Column("sender", sa.String(320), nullable=True))
    op.add_column(
        "memories", sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_memories_sender", "memories", ["user_id", "sender"])


def downgrade() -> None:
    op.drop_index("ix_memories_sender", table_name="memories")
    op.drop_column("memories", "occurred_at")
    op.drop_column("memories", "sender")
    op.drop_index("ix_chunks_occurred_at", table_name="chunks")
    op.drop_column("chunks", "meta")
    op.drop_column("chunks", "occurred_at")
