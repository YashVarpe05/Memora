"""Durable indexing and multiple locations for identical documents."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "memories",
        sa.Column(
            "device_paths", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.execute(
        "UPDATE memories SET device_paths=jsonb_build_array(device_path) WHERE device_path IS NOT NULL"
    )
    op.create_table(
        "index_jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("device_path", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(1024)),
        sa.Column("result", pg.JSONB()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "retry_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "content_hash", "device_path"),
    )
    op.create_index("ix_index_jobs_user_id", "index_jobs", ["user_id"])
    op.execute("ALTER TABLE index_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE index_jobs FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY index_jobs_owner ON index_jobs
        USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
        WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)""")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON index_jobs TO memora_app")


def downgrade():
    op.drop_table("index_jobs")
    op.drop_column("memories", "device_paths")
