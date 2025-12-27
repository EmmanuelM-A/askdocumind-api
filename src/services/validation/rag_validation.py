"""
Handles input validation for user queries, file paths, and URLs.
"""

import os
import re
import html
from typing import Optional, Tuple, List
from urllib.parse import urlparse

from pydantic import BaseModel, Field, validator, field_validator
from sqlalchemy import UUID

from src.components.ingestion.document import FileDocument
from src.config.configs import settings
from src.errors.custom_exceptions import throw_unprocessable_entity_error
from src.logger.base_logger import BaseLogger

# TODO: USE PYDANTIC FOR VALIDATION?


def sanitize_query(query: str, logger: BaseLogger) -> str:
    """Sanitize user query and return warnings if any."""

    if not query:
        throw_unprocessable_entity_error(
            message="Query cannot be empty", error_code="EMPTY_QUERY"
        )

    # Remove potential script tags and HTML
    query = html.escape(query)

    # Remove any remaining HTML tags
    query = re.sub(r"<[^>]+>", "", query)

    # Remove excessive whitespace
    query = re.sub(r"\s+", " ", query).strip()

    # Check for suspicious patterns
    suspicious_patterns = [  # TODO: EXPAND THIS LIST AND STORE ELSEWHERE
        r"<script[^>]*>",
        r"javascript:",
        r"data:text/html",
        r"eval\s*\(",
        r"document\.",
        r"window\.",
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            logger.warning("Potentially malicious content removed from query")
            query = re.sub(pattern, "", query, flags=re.IGNORECASE)

    # Truncate if too long
    if len(query) > settings.vector.MAX_QUERY_LENGTH:
        query = query[: settings.vector.MAX_QUERY_LENGTH]
        logger.warning(
            f"Query truncated to {settings.vector.MAX_QUERY_LENGTH} characters"
        )

    return query


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

    @field_validator("user_query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Ensure query is not just whitespace."""

        if not v.strip():
            raise ValueError("user_query cannot be empty or whitespace")

        return v.strip()
