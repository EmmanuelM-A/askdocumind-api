"""add unique constraint for document session filename

Revision ID: 7c2f1a9d4b6e
Revises: ce05f8fa413a
Create Date: 2026-04-13 20:40:00.000000

"""
from typing import Sequence, Union

from alembic import op  # type: ignore[attr-defined]


# revision identifiers, used by Alembic.
revision: str = "7c2f1a9d4b6e"
down_revision: Union[str, Sequence[str], None] = "ce05f8fa413a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINT_NAME = "uq_document_session_filename"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        CONSTRAINT_NAME,
        "document",
        ["session_id", "filename"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(CONSTRAINT_NAME, "document", type_="unique")


