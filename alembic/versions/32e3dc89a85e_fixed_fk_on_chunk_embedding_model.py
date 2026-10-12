"""fixed fk on chunk embedding model

Revision ID: 32e3dc89a85e
Revises: 489a99304d5a
Create Date: 2026-10-12 15:14:12.755219
"""

from typing import Sequence, Union

from alembic import op

revision: str = "32e3dc89a85e"
down_revision: Union[str, Sequence[str], None] = "489a99304d5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(
        "chunk_embeddings_document_id_chat_session_id_fkey",
        "chunk_embeddings",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_chunk_embeddings_document_id_documents",
        "chunk_embeddings",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_foreign_key(
        "fk_chunk_embeddings_chat_session_id_chat_sessions",
        "chunk_embeddings",
        "chat_sessions",
        ["chat_session_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "fk_chunk_embeddings_chat_session_id_chat_sessions",
        "chunk_embeddings",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_chunk_embeddings_document_id_documents",
        "chunk_embeddings",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "chunk_embeddings_document_id_chat_session_id_fkey",
        "chunk_embeddings",
        "documents",
        ["document_id", "chat_session_id"],
        ["id", "chat_session_id"],
        ondelete="CASCADE",
    )
