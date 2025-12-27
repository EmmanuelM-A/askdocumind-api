"""
Utility functions and classes for various operations.
"""

import hashlib
import os


def does_file_exist(file_path) -> bool:
    """Returns True if the specified file path exists and false otherwise."""
    return os.path.exists(file_path)


def generate_content_hash(content: str) -> str:
    """
    Generate an SHA-256 hash for the given content.

    Args:
        content: String content to hash.

    Returns:
        Hexadecimal hash string.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
