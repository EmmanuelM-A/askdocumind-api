"""
Utility functions for storage services.
"""

from src.exceptions import unprocessable_content_error


def validate_key(key: str) -> str:
    """
    Reject keys with traversal parts, empty parts, or odd characters.
    """
    if not key or key.startswith("/") or "\\" in key or "\x00" in key:
        raise unprocessable_content_error(
            message="The storage key provided is invalid",
            error_code="INVALID_STORAGE_KEY",
        )

    if any(part in ("", ".", "..") for part in key.split("/")):
        raise unprocessable_content_error(
            message="The storage key provided is invalid",
            error_code="INVALID_STORAGE_KEY",
        )

    return key


def normalize_prefix(prefix: str) -> str:
    """
    Validate a folder prefix and remove the trailing slash.
    """
    return validate_key(prefix.rstrip("/"))
