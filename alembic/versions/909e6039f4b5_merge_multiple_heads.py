"""merge multiple heads

Revision ID: 909e6039f4b5
Revises: 7c2f1a9d4b6e, b72f4ddf7d1a
Create Date: 2026-05-08 03:12:20.114579

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '909e6039f4b5'
down_revision: str | Sequence[str] | None = ('7c2f1a9d4b6e', 'b72f4ddf7d1a')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
