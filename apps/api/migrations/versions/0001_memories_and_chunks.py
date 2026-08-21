"""memories and chunks, with RLS

RLS ships here, in the migration that creates the tables - never as a follow-up.
See the RLS section of CLAUDE.md. Auth arrives in phase 2; the policies do not
wait for it, because a table that exists without its policy is a table someone
queries without one.

Revision ID: 0001
Revises:
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USER_TABLES = ("memories", "chunks")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_memories_user_id", "memories", ["user_id"])

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "memory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("contextual_prefix", sa.String(512), nullable=False, server_default=""),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(768), nullable=False),
    )
    op.create_index("ix_chunks_user_id", "chunks", ["user_id"])
    op.create_index("ix_chunks_memory_id", "chunks", ["memory_id"])

    # HNSW rather than IVFFlat: no training pass, so it behaves sensibly while the
    # table is small and still holds up as it grows.
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    for table in USER_TABLES:
        # FORCE matters: without it the table owner bypasses its own policy, and
        # migrations run as the owner.
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # Two-arg current_setting: the one-arg form raises when unset, this returns
        # NULL, and `user_id = NULL` matches nothing - so broken session-var
        # plumbing fails closed instead of open.
        #
        # NULLIF on top of it: a var that is SET but empty returns '', and ''::uuid
        # raises instead of matching nothing. Without this, half-configured plumbing
        # is a 500 rather than zero rows.
        op.execute(
            f"""
            CREATE POLICY {table}_owner ON {table}
              USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
              WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
            """
        )
        # ALTER DEFAULT PRIVILEGES in infra/db/init covers databases created after
        # that script existed. Granting explicitly makes the migration self-contained.
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO memora_app")


def downgrade() -> None:
    for table in USER_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
    op.drop_table("chunks")
    op.drop_table("memories")
