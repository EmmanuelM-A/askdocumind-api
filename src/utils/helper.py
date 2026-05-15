"""
Utility functions and classes for various operations.
"""

import hashlib
import os


def does_file_exist(file_path) -> bool:
    """Returns True if the specified file path exists and false otherwise."""
    return os.path.exists(file_path)
