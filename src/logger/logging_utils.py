"""
Contains logging utils used only for logging purposes.
"""

from enum import Enum
import logging
from typing import Literal



LogTo = Literal["CONSOLE", "FILE", "BOTH"]


LogLevel = Literal["CRITICAL", "FATAL", "ERROR", "WARNING", "WARN", "INFO", "DEBUG"]


class ColorFormatter(logging.Formatter):
    """Custom formatter to add color to log messages."""

    COLORS = {
        logging.DEBUG: "\033[94m",  # Blue
        logging.INFO: "\033[92m",  # Green
        logging.WARNING: "\033[93m",  # Yellow
        logging.ERROR: "\033[91m",  # Red
        logging.CRITICAL: "\033[95m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, self.RESET)
        return f"{color}{super().format(record)}{self.RESET}"


def get_log_level(level: str) -> int:
    """
    Converts the log level string into its numerical counterpart.
    """

    level_mappings = {
        "CRITICAL": 50,
        "FATAL": 50,
        "ERROR": 40,
        "WARNING": 30,
        "WARN": 30,
        "INFO": 20,
        "DEBUG": 10,
    }

    return level_mappings.get(level.upper(), 20)


class MaxLevelFilter(logging.Filter):
    """
    Allow only log records with levelno <= max_level.

    We'll use this to ensure app.log receives only DEBUG/INFO (non-warning/non-error)
    while warnings and errors go to a separate error.log.
    """

    def __init__(self, max_level: int):
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level
