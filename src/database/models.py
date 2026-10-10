"""
Imports all SQLAlchemy model modules so they register on Base.metadata.
This module exists only to be imported by Alembic's env.py, never by
application code or by the models themselves.
"""

from src.auth.models.user import User
from src.chat_session.models.chat_session import ChatSession
from src.chat_session.models.chat_message import ChatMessage
from src.uploads.models.document import Document
from src.rag.models.chunk_embedding import ChunkEmbedding
