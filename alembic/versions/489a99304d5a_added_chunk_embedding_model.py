"""added chunk embedding model

Revision ID: 489a99304d5a
Revises: 8c2df2c8f548
Create Date: 2026-10-10 14:16:05.884800

"""

from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "489a99304d5a"
down_revision: Union[str, Sequence[str], None] = "8c2df2c8f548"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Hardcoded on purpose. A migration must not change when config changes.
EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # The composite foreign key below needs this constraint to exist first.
    op.create_unique_constraint(
        "uq_document_id_session", "documents", ["id", "chat_session_id"]
    )

    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("chat_session_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(EMBEDDING_DIMENSIONS),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "chat_session_id"],
            ["documents.id", "documents.chat_session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_chunk_document_index"
        ),
    )
    op.create_index(
        "ix_chunk_embeddings_chat_session_id",
        "chunk_embeddings",
        ["chat_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_chunk_embeddings_embedding_hnsw",
        "chunk_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chunk_embeddings_embedding_hnsw", table_name="chunk_embeddings")
    op.drop_index("ix_chunk_embeddings_chat_session_id", table_name="chunk_embeddings")
    op.drop_table("chunk_embeddings")

    # Drop after the table, because the foreign key depends on this constraint.
    op.drop_constraint("uq_document_id_session", "documents", type_="unique")

    # The vector extension stays in place. Other objects may depend on it.
