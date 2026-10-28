"""
Logging configuration for the AskDocuMind API application.
"""

import logging
import logging.config
import sys
from pathlib import Path
from typing import ClassVar

from src.config.configs import settings


class ColorFormatter(logging.Formatter):
    """
    Adds ANSI color by level. Colors turn off when output is not a terminal.
    """

    COLORS: ClassVar[dict[int, str]] = {
        logging.DEBUG: "\033[94m",
        logging.INFO: "\033[92m",
        logging.WARNING: "\033[93m",
        logging.ERROR: "\033[91m",
        logging.CRITICAL: "\033[95m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not sys.stdout.isatty():
            return message
        color = self.COLORS.get(record.levelno, self.RESET)
        return f"{color}{message}{self.RESET}"


class _BelowWarningFilter(logging.Filter):
    """
    Lets through only records below WARNING, so app.log holds DEBUG and INFO.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.WARNING


def setup_logging() -> None:
    """
    Configure logging for the whole application. Call once at startup.
    """
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "file": {
                "()": ColorFormatter,
                "format": settings.logging.LOG_FORMAT,
                "datefmt": settings.logging.DATE_FORMAT,
            },
        },
        "filters": {
            "below_warning": {"()": _BelowWarningFilter},
        },
        "handlers": {
            "app_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "app.log"),
                "maxBytes": 10_000_000,
                "backupCount": 5,
                "encoding": "utf-8",
                "filters": ["below_warning"],
                "formatter": "file",
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "error.log"),
                "maxBytes": 10_000_000,
                "backupCount": 5,
                "encoding": "utf-8",
                "level": "WARNING",
                "formatter": "file",
            },
        },
        "root": {
            "level": settings.logging.LOG_LEVEL.upper(),
            "handlers": ["app_file", "error_file"],
        },
    }

    logging.config.dictConfig(config)
