"""overhauled all db models

Revision ID: 8c2df2c8f548
Revises: b1e7c4a29f3d
Create Date: 2026-10-10 09:12:31.537678

"""

from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8c2df2c8f548"
down_revision: Union[str, Sequence[str], None] = "b1e7c4a29f3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop old tables, children first
    op.drop_table("document_chunk")
    op.drop_table("document")
    op.drop_table("chat_message")
    op.drop_table("chat_session")
    op.drop_table("user")

    # Drop old enum types
    op.execute("DROP TYPE IF EXISTS chatmessagerole")
    op.execute("DROP TYPE IF EXISTS processingstatus")
    op.execute("DROP TYPE IF EXISTS documentsourcetype")

    # Create new tables, parents first
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chat_sessions_user_id"), "chat_sessions", ["user_id"], unique=False
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chat_session_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("USER", "ASSISTANT", "SYSTEM", name="chatmessagerole"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chat_session_id"], ["chat_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_chat_messages_chat_session_id"),
        "chat_messages",
        ["chat_session_id"],
        unique=False,
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("chat_session_id", sa.UUID(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "UPLOADED",
                "PROCESSING",
                "COMPLETED",
                "FAILED",
                name="documentstatus",
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chat_session_id"], ["chat_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chat_session_id",
            "original_filename",
            name="uq_document_chat_session_filename",
        ),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        op.f("ix_documents_chat_session_id"),
        "documents",
        ["chat_session_id"],
        unique=False,
    )
    op.create_index(op.f("ix_documents_status"), "documents", ["status"], unique=False)
    op.create_index(
        op.f("ix_documents_updated_at"), "documents", ["updated_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop new tables, children first
    op.drop_index(op.f("ix_documents_updated_at"), table_name="documents")
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_chat_session_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_chat_messages_chat_session_id"), table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index(op.f("ix_chat_sessions_user_id"), table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_table("users")

    # Drop new enum types
    op.execute("DROP TYPE IF EXISTS chatmessagerole")
    op.execute("DROP TYPE IF EXISTS documentstatus")

    # Recreate old tables, parents first
    op.create_table(
        "user",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "last_seen_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("user_pkey")),
    )
    op.create_index(
        op.f("ix_user_last_seen_at"), "user", ["last_seen_at"], unique=False
    )
    op.create_index(op.f("ix_user_created_at"), "user", ["created_at"], unique=False)
    op.create_table(
        "chat_session",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("title", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column("user_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("chat_session_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("chat_session_pkey")),
    )
    op.create_table(
        "document",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("session_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "source", sa.VARCHAR(length=255), autoincrement=False, nullable=False
        ),
        sa.Column("source_size", sa.BIGINT(), autoincrement=False, nullable=False),
        sa.Column(
            "processing_status",
            postgresql.ENUM(
                "PENDING", "PROCESSING", "COMPLETED", "FAILED", name="processingstatus"
            ),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "source_type",
            postgresql.ENUM("UPLOAD", "WEB_SEARCH", name="documentsourcetype"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_session.id"],
            name=op.f("document_session_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("document_pkey")),
        sa.UniqueConstraint(
            "session_id",
            "source",
            name=op.f("uq_document_session_source"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )
    op.create_table(
        "document_chunk",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("document_id", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("chunk_text", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.vector.VECTOR(dim=1536),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column("chat_session_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_session_id"],
            ["chat_session.id"],
            name=op.f("fk_document_chunk_chat_session_id_chat_session"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("document_chunk_document_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("document_chunk_pkey")),
    )
    op.create_table(
        "chat_message",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("session_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("USER", "ASSISTANT", "SYSTEM", name="chatmessagerole"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("content", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "sources",
            postgresql.ARRAY(sa.VARCHAR()),
            autoincrement=False,
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_session.id"],
            name=op.f("chat_message_session_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("chat_message_pkey")),
    )
