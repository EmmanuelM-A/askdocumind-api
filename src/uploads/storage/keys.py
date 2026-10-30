"""
Builds object storage keys. Every key a chat session owns starts with its
prefix, so deleting the prefix removes all of the session's files. Build keys
here only, so saving and deleting can't drift apart.
"""

from uuid import UUID


def chat_session_prefix(chat_session_id: UUID) -> str:
    return f"{chat_session_id}/"


def document_object_key(chat_session_id: UUID, document_id: UUID) -> str:
    return f"{chat_session_prefix(chat_session_id)}{document_id}"
