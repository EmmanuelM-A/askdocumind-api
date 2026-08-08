"""rename document filename/file_size to source/source_size

Revision ID: d3a9f5c1e2b7
Revises: ff3dea15a12f
Create Date: 2026-07-24 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3a9f5c1e2b7"
down_revision: str | Sequence[str] | None = "ff3dea15a12f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("document", "filename", new_column_name="source")
    op.alter_column("document", "file_size", new_column_name="source_size")
    op.drop_constraint(
        "uq_document_session_filename", "document", type_="unique"
    )
    op.create_unique_constraint(
        "uq_document_session_source", "document", ["session_id", "source"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_document_session_source", "document", type_="unique"
    )
    op.create_unique_constraint(
        "uq_document_session_filename", "document", ["session_id", "filename"]
    )
    op.alter_column("document", "source_size", new_column_name="file_size")
    op.alter_column("document", "source", new_column_name="filename")
