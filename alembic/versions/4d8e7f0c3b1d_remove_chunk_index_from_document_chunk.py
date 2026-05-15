"""remove chunk_index from document_chunk

Revision ID: 4d8e7f0c3b1d
Revises: 2b6c5f0a1d9e
Create Date: 2026-05-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4d8e7f0c3b1d"
down_revision: Union[str, Sequence[str], None] = "2b6c5f0a1d9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("document_chunk", "chunk_index")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "document_chunk",
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

