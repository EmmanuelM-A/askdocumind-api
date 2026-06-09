"""
Handles input validation for user queries, file paths, and URLs.
"""

import re
import html
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlparse

from fastapi import UploadFile
from pydantic import BaseModel, Field, field_validator
from uuid import UUID

from src.database.repository.interfaces import ChatSessionRepositoryInterface
from src.database.repository.interfaces import ChatSessionSearchCriteria
from src.api.services.auth.anonymous_identity import require_current_anonymous_user_id

from src.config.configs import settings
from src.errors.custom_exceptions import (
    unprocessable_entity_error,
    not_found_error,
)
from src.logger.base_logger import BaseLogger

# TODO: USE PYDANTIC FOR VALIDATION?


def validate_and_sanitize_query(query: str, logger: BaseLogger) -> str:
    """Sanitize user query and return the sanitized string.

    The function is idempotent: repeated calls produce the same output. It
    performs a canonicalization (unescape) -> cleaning -> escape pipeline and
    only logs when the canonicalized value changed (so nested callers won't
    produce duplicate log entries).
    """

    # Basic presence check
    if query is None:
        raise unprocessable_entity_error(
            message="Query cannot be empty", error_code="EMPTY_QUERY"
        )

    # Normalize input to string and ensure not empty/whitespace
    raw = str(query)
    if not raw.strip():
        raise unprocessable_entity_error(
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
        raise unprocessable_entity_error(
            message="URL cannot be empty", error_code="EMPTY_URL"
        )

    parsed = urlparse(url)

    # Must have scheme and netloc
    if not parsed.scheme or not parsed.netloc:
        raise unprocessable_entity_error(
            message="Invalid URL format", error_code="INVALID_URL_FORMAT"
        )

    # Only allow HTTP/HTTPS
    if parsed.scheme not in ["http", "https"]:
        raise unprocessable_entity_error(
            message="Only HTTP and HTTPS URLs are allowed",
            error_code="INVALID_URL_SCHEME",
        )

    # Block local/private addresses
    blocked_hosts = ["localhost", "127.0.0.1", "0.0.0.0"]
    if any(blocked in parsed.netloc.lower() for blocked in blocked_hosts):
        raise unprocessable_entity_error(
            message="Local and private addresses are not allowed",
            error_code="BLOCKED_URL_HOST",
        )

    return True


async def check_if_chat_exists(
    chat_id: UUID, chat_session_repo: ChatSessionRepositoryInterface
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

    current_user_id = require_current_anonymous_user_id()

    chat = await chat_session_repo.get_by_criteria(
        ChatSessionSearchCriteria(id=chat_id, user_id=current_user_id)
    )

    if chat is None:
        raise not_found_error(
            message=f"Chat session with ID {chat_id} not found.",
            error_code="CHAT_SESSION_NOT_FOUND",
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

        return validate_and_sanitize_query(query=value, logger=BaseLogger(__name__))


class UploadDocumentsRequest(BaseModel):
    """
    Request model for document uploads.
    """

    documents: List[UploadFile] = Field(
        ...,
        description="List of file documents to be uploaded",
        min_length=1,
        max_length=5,
    )
    chat_id: UUID = Field(..., description="The chat session identifier")

    @field_validator("documents", mode="before")
    @classmethod
    def validate_file_extensions(cls, files: List[UploadFile]) -> List[UploadFile]:
        allowed = {ext.lstrip(".") for ext in settings.files.ALLOWED_FILE_EXTENSIONS}
        invalid = [
            f.filename
            for f in files
            if Path(f.filename or "").suffix.lower().lstrip(".") not in allowed
        ]
        if invalid:
            raise ValueError(
                f"Unsupported file type(s): {', '.join(invalid)}. "
                f"Allowed: {', '.join(sorted(allowed))}"
            )
        return files


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

    chat_id: UUID = Field(..., description="The chat session identifier")


class DeleteUploadedDocumentRequest(BaseModel):
    """Request model for deleting an uploaded document."""

    chat_id: UUID = Field(..., description="The chat session identifier")
    document_id: UUID = Field(..., description="The document identifier")


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
