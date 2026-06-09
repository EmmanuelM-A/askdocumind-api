"""add chat_session_id to document_chunk

Revision ID: 2b6c5f0a1d9e
Revises: a477581362a0
Create Date: 2026-05-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2b6c5f0a1d9e"
down_revision: Union[str, Sequence[str], None] = "a477581362a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "document_chunk",
        sa.Column("chat_session_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_document_chunk_chat_session_id_chat_session",
        "document_chunk",
        "chat_session",
        ["chat_session_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_document_chunk_chat_session_id_chat_session",
        "document_chunk",
        type_="foreignkey",
    )
    op.drop_column("document_chunk", "chat_session_id")




