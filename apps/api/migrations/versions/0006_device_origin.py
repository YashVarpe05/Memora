"""Where a memory came from on the phone, and whether it is still there.

Revision ID: 0006
Revises: 0005

Two columns on `memories`, both for files discovered by the device scan rather than
uploaded by hand.

**`device_path`** is the MediaStore content URI the file was found at. It exists to answer
"is this still on the phone?", which needs a stable identity that is not the content hash:
the hash identifies the BYTES, and the question here is about a LOCATION. Two copies of the
same photo in two folders share a hash; deleting one does not remove the other.

**`removed_at`** records that the file is gone from the device while the memory stays.
That is the product's premise applied to its own storage: "I know I had it" is the problem
statement, so losing the ability to find something because it was tidied away would be the
system reproducing the very failure it exists to fix. The blob is the user's to delete;
the record of having seen it is what makes the search work. Erasure on request remains a
separate and complete operation, and is unaffected by this.

No RLS work here. `memories` already carries ENABLE + FORCE and its policy from the
migration that created it, and a policy attaches to the table rather than to its columns,
so new columns are covered the moment they exist. A follow-up policy would be the mistake
this project has written down; a follow-up *column* on an already-protected table is not.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memories", sa.Column("device_path", sa.String(1024), nullable=True))
    op.add_column(
        "memories",
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Reconciliation looks up "everything this user has from a device" on every full scan,
    # and marks the absent ones. Without this that is a sequential scan of the corpus.
    op.create_index(
        "ix_memories_user_device_path",
        "memories",
        ["user_id", "device_path"],
        unique=False,
        postgresql_where=sa.text("device_path IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_memories_user_device_path", table_name="memories")
    op.drop_column("memories", "removed_at")
    op.drop_column("memories", "device_path")
