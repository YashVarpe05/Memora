"""Image embeddings, so a document can be found by what it looks like.

Revision ID: 0005
Revises: 0004

A separate table rather than a column on `chunks`, for three reasons:

1. **Different dimensionality.** CLIP ViT-B/32 is 512; the text index is 768. One pgvector
   index cannot serve both, and a nullable second vector column would put an unused
   512-float column on every text chunk.
2. **Different distance semantics.** A CLIP similarity of 0.28 is a strong match; the text
   pipeline treats 0.5 as weak. Sharing a column invites a threshold written for one scale
   being applied to the other, which is this project's most repeated bug.
3. **Different lifecycle.** Re-embedding images after a model change must not touch text.

**RLS ships here, in the migration that creates the table.** Never a follow-up: a
user-owned table without FORCE ROW LEVEL SECURITY from birth is a table that spends some
window enforcing nothing, and every test passes throughout.
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None

DIMS = 512


def upgrade() -> None:
    op.create_table(
        "image_embeddings",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "memory_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(DIMS), nullable=False),
        # Pinned, and stored per row: changing the model invalidates every vector, and a
        # mixed table would silently compare embeddings from two different spaces.
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_image_embeddings_memory", "image_embeddings", ["user_id", "memory_id"]
    )

    op.execute("ALTER TABLE image_embeddings ENABLE ROW LEVEL SECURITY")
    # FORCE, or the owning role bypasses its own policy and the test passes anyway.
    op.execute("ALTER TABLE image_embeddings FORCE ROW LEVEL SECURITY")
    # Two-arg current_setting: the one-arg form RAISES when the session var is unset,
    # while this returns NULL, and `user_id = NULL` matches nothing. Broken session-var
    # plumbing therefore fails closed instead of open.
    op.execute(
        """
        CREATE POLICY image_embeddings_owner ON image_embeddings
        USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON image_embeddings TO memora_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS image_embeddings_owner ON image_embeddings")
    op.drop_index("ix_image_embeddings_memory", table_name="image_embeddings")
    op.drop_table("image_embeddings")
