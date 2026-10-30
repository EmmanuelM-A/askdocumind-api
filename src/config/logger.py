"""
Logging configuration for the AskDocuMind API application.
"""

import logging
import logging.config
from pathlib import Path
from typing import Any

from src.config.configs import settings

# Third-party loggers that flood the files at DEBUG, kept at WARNING so
# LOG_LEVEL only controls the app's own output
_NOISY_LOGGERS = ("botocore", "boto3", "s3transfer", "urllib3", "httpcore", "httpx")


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

    config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "file": {
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
        "loggers": {name: {"level": "WARNING"} for name in _NOISY_LOGGERS},
        "root": {
            "level": settings.logging.LOG_LEVEL.upper(),
            "handlers": ["app_file", "error_file"],
        },
    }

    # Hosts like Railway only collect stdout, and the log files are lost with
    # the container. Development keeps the console clean.
    if settings.server.ENV != "development":
        config["handlers"]["console"] = {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "file",
        }
        config["root"]["handlers"].append("console")

    logging.config.dictConfig(config)
