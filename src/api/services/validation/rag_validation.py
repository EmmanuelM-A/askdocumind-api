"""
Handles input validation for user queries, file paths, and URLs.
"""

import re
import html
from typing import Optional, Tuple, List, TYPE_CHECKING
from urllib.parse import urlparse

from fastapi import UploadFile
from pydantic import BaseModel, Field, field_validator
from uuid import UUID

from src.database.repository.interfaces import ChatSessionRepositoryInterface

# Avoid importing RAGChatbot at module import time to prevent circular imports;
# import it only for type checking.
if TYPE_CHECKING:
    from src.components.chatbot.core import RAGChatbot

from src.components.ingestion.document import FileDocument
from src.config.configs import settings
from src.errors.custom_exceptions import (
    throw_unprocessable_entity_error,
    throw_not_found_error,
)
from src.logger.base_logger import BaseLogger

# TODO: USE PYDANTIC FOR VALIDATION?


def sanitize_query(query: str, logger: BaseLogger) -> str:
    """Sanitize user query and return the sanitized string.

    The function is idempotent: repeated calls produce the same output. It
    performs a canonicalization (unescape) -> cleaning -> escape pipeline and
    only logs when the canonicalized value changed (so nested callers won't
    produce duplicate log entries).
    """

    # Basic presence check
    if query is None:
        throw_unprocessable_entity_error(
            message="Query cannot be empty", error_code="EMPTY_QUERY"
        )

    # Normalize input to string and ensure not empty/whitespace
    raw = str(query)
    if not raw.strip():
        throw_unprocessable_entity_error(
            message="Query cannot be empty", error_code="EMPTY_QUERY"
        )

    # Canonicalize HTML entities so we operate on raw text consistently.
    canonical = html.unescape(raw)

    # Remove HTML tags
    cleaned = re.sub(r"<[^>]+>", "", canonical)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # TODO: Add more sophisticated XSS/malicious content detection in separate file
    # Remove suspicious patterns (without logging per pattern to avoid noise)
    suspicious_patterns = [
        r"<script[^>]*>",
        r"javascript:",
        r"data:text/html",
        r"eval\s*\(",
        r"document\.",
        r"window\.",
    ]

    changed = False
    for pattern in suspicious_patterns:
        if re.search(pattern, cleaned, re.IGNORECASE):
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
            changed = True

    # Truncate if too long (operate on the canonical cleaned text length)
    max_len = settings.vector.MAX_QUERY_LENGTH
    if max_len and len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
        changed = True

    # Log a single warning only if something was actually removed/truncated
    if changed:
        logger.warning("Potentially malicious content removed or query truncated")

    # Escape once to produce a safe string for downstream usage
    result = html.escape(cleaned)

    return result


def validate_url(url: str) -> bool:
    """Validate URL for web searches."""

    if not url:
        throw_unprocessable_entity_error(
            message="URL cannot be empty", error_code="EMPTY_URL"
        )

    parsed = urlparse(url)

    # Must have scheme and netloc
    if not parsed.scheme or not parsed.netloc:
        throw_unprocessable_entity_error(
            message="Invalid URL format", error_code="INVALID_URL_FORMAT"
        )

    # Only allow HTTP/HTTPS
    if parsed.scheme not in ["http", "https"]:
        throw_unprocessable_entity_error(
            message="Only HTTP and HTTPS URLs are allowed",
            error_code="INVALID_URL_SCHEME",
        )

    # Block local/private addresses
    blocked_hosts = ["localhost", "127.0.0.1", "0.0.0.0"]
    if any(blocked in parsed.netloc.lower() for blocked in blocked_hosts):
        throw_unprocessable_entity_error(
            message="Local and private addresses are not allowed",
            error_code="BLOCKED_URL_HOST",
        )

    return True


def validate_document_content(
    document: FileDocument, logger: BaseLogger
) -> Tuple[bool, Optional[str]]:
    """
    Validate document content before processing.

    Args:
        document: The FileDocument instance to validate.
        logger: The logger instance for logging warnings.

    Returns:
        A tuple containing a boolean indicating if the document is valid,
        and the cleaned content or None.
    """

    if not document or not document.content:
        return False, None

    content = document.content.strip()
    if len(content) < settings.app.MIN_DOCUMENT_CONTENT_LENGTH:
        logger.warning(f"Document {document.metadata.filename} too short, skipping")
        return False, None

    if len(content) > settings.app.MAX_DOCUMENT_CONTENT_LENGTH:
        if settings.app.IS_TRUNCATION_ENABLED:
            logger.warning(
                f"Document {document.metadata.filename} too large, truncating"
            )
            document.content = (
                content[: settings.app.MAX_DOCUMENT_CONTENT_LENGTH] + "... [TRUNCATED]"
            )
        else:
            logger.warning(f"Document {document.metadata.filename} too large, skipping")
            return False, None

    return True, content


async def check_if_chat_exists(
    chat_id: UUID,
    chat_session_repo: ChatSessionRepositoryInterface,
    chatbot: "RAGChatbot",
) -> None:
    """
    Check if the chat session and corresponding chat vector store exist.

    Args:
        chat_id: The UUID of the chat session to check.
        chat_session_repo: The repository to check chat session existence.
        chatbot: The RAGChatbot instance to check vector store existence.

    Raises:
        NotFoundError: If the chat session or vector store does not exist.
    """

    if not await chat_session_repo.exists(chat_id):
        throw_not_found_error(
            message=f"Chat session with ID {chat_id} not found.",
            error_code="CHAT_SESSION_NOT_FOUND",
        )

    if not chatbot.chat_exists(index_chat_id=str(chat_id)):
        throw_not_found_error(
            message=f"Chat with ID {chat_id} not found in vector store.",
            error_code="CHAT_NOT_FOUND_IN_VECTOR_STORE",
        )


class ChatRequest(BaseModel):
    """
    Request model for chat interactions.
    """

    user_query: str = Field(
        ...,
        min_length=settings.app.MIN_QUERY_LENGTH,
        max_length=settings.app.MAX_QUERY_LENGTH,
        description="The user's chat query",
    )
    chat_id: UUID = Field(..., description="The chat session identifier")
    web_search_enabled: bool = Field(
        False, description="Flag to enable web search for the query"
    )

    @field_validator("user_query", mode="before")
    def validate_query(cls, value: str) -> str:
        """Ensure query is not just whitespace."""

        return sanitize_query(query=value, logger=BaseLogger(__name__))


class UploadDocumentsRequest(BaseModel):
    """
    Request model for document uploads.
    """

    documents: List[UploadFile] = Field(
        ...,
        description="List of file documents to be uploaded",
        min_length=1,
        max_length=settings.files.MAX_FILES_PER_UPLOAD,
    )
    chat_id: UUID = Field(..., description="The chat session identifier")
    vector_id: UUID = Field(
        ..., description="The vector store identifier for the chat session"
    )


class FetchUploadedDocumentsRequest(BaseModel):
    """
    Request model for fetching uploaded documents.
    """

    document_ids: Optional[List[UUID]] = Field(
        None,
        description="Optional list of document IDs to retrieve. "
        "If not provided, all documents will be fetched.",
        min_length=1,
    )
    chat_id: UUID = Field(..., description="The chat session identifier")


class FetchDocumentMetadataRequest(BaseModel):
    """
    Request model for fetching document metadata.
    """

    document_ids: List[UUID] = Field(
        ...,
        description="List of document IDs to retrieve metadata for",
        min_length=1,
    )
    chat_id: UUID = Field(..., description="The chat session identifier")


class CreateChatSessionRequest(BaseModel):
    """
    Request model for creating a new chat session.
    """


class DeleteChatSessionRequest(BaseModel):
    """
    Request model for deleting a chat session.
    """

    chat_id: UUID = Field(..., description="The chat session identifier")


class ListChatSessionsRequest(BaseModel):
    """
    Request model for listing chat sessions.
    """


class FetchChatHistoryRequest(BaseModel):
    """
    Request model for fetching chat history.
    """

    chat_id: UUID = Field(..., description="The chat session identifier")
