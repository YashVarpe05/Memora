"""Document type on memories, for refusal by type agreement.

Revision ID: 0004
Revises: 0003

Nullable, and null is the normal case. Most documents have no recognised type, and a
query that names no type never reaches the refusal check at all.

No RLS statements here: `memories` already has ENABLE + FORCE ROW LEVEL SECURITY and its
policy from 0001, and adding a column to a table does not change its policy. The rule in
CLAUDE.md is that a table ships its policy in the migration that CREATES it, which 0001
did.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memories", sa.Column("document_type", sa.String(32), nullable=True))
    # Refusal asks "does this user hold any document of type X". That is a scan over one
    # user's rows filtered by type, so the index leads with user_id.
    op.create_index(
        "ix_memories_user_document_type",
        "memories",
        ["user_id", "document_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_memories_user_document_type", table_name="memories")
    op.drop_column("memories", "document_type")
