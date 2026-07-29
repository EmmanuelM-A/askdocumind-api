"""add source_type to document

Revision ID: a1f6c2d8b3e4
Revises: d3a9f5c1e2b7
Create Date: 2026-07-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f6c2d8b3e4"
down_revision: str | Sequence[str] | None = "d3a9f5c1e2b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


document_source_type_enum = sa.Enum(
    "UPLOAD", "WEB_SEARCH", name="documentsourcetype"
)


def upgrade() -> None:
    """Upgrade schema."""
    document_source_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "document",
        sa.Column(
            "source_type",
            document_source_type_enum,
            nullable=False,
            server_default="UPLOAD",
        ),
    )
    op.alter_column("document", "source_type", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("document", "source_type")
    document_source_type_enum.drop(op.get_bind(), checkfirst=True)
