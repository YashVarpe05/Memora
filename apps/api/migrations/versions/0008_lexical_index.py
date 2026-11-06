"""Allow text indexing without a semantic embedding provider."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("chunks", "embedding", nullable=True)


def downgrade():
    # Refuse downgrade if lexical rows exist; never silently erase indexed text.
    op.alter_column("chunks", "embedding", nullable=False)
