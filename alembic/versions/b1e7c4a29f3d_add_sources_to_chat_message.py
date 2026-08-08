"""add sources to chat_message

Revision ID: b1e7c4a29f3d
Revises: a1f6c2d8b3e4
Create Date: 2026-08-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1e7c4a29f3d"
down_revision: str | Sequence[str] | None = "a1f6c2d8b3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chat_message",
        sa.Column("sources", postgresql.ARRAY(sa.String()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chat_message", "sources")
