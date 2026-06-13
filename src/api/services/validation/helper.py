"""
Handles input validation for user queries, file paths, and URLs.
"""

import html
import re


from uuid import UUID

from src.database.models import ChatSession
from src.database.repository.interfaces import ChatSessionRepositoryInterface
from src.database.repository.interfaces import ChatSessionSearchCriteria

from src.config.configs import settings
from src.errors.custom_exceptions import not_found_error, unprocessable_entity_error
from src.logger.base_logger import BaseLogger


async def check_if_chat_exists(
    chat_id: UUID, owner_id: UUID, chat_session_repo: ChatSessionRepositoryInterface
) -> ChatSession:
    """
    Check if a chat session exists and is owned by the specified user.
    """

    chat = await chat_session_repo.get_by_criteria(
        ChatSessionSearchCriteria(id=chat_id, user_id=owner_id)
    )

    if chat is None:
        raise not_found_error(
            message=f"Chat session with ID {chat_id} not found.",
            error_code="CHAT_SESSION_NOT_FOUND",
        )

    return chat


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
