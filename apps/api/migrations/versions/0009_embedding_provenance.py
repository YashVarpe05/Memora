"""Track text-vector coordinate spaces without guessing legacy provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chunks", sa.Column("embedding_model", sa.String(512), nullable=True))
    op.create_index("ix_chunks_owner_embedding_model", "chunks", ["user_id", "embedding_model"])


def downgrade():
    op.drop_index("ix_chunks_owner_embedding_model", table_name="chunks")
    op.drop_column("chunks", "embedding_model")
