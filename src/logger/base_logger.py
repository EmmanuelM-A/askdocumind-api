"""
Logging utility class for the application and its modules.
"""

import logging
import os
import sys
from typing import List, Optional
from src.logger.logging_utils import (
    ColorFormatter,
    LogLevel,
    LogTo,
    get_log_level,
    MaxLevelFilter,
)
from src.config.configs import settings


class BaseLogger:
    """
    Base logging class for consistent application-wide logging.
    Provides colorized console output and optional file-based logging.
    """

    def __init__(
        self,
        name: str,
        log_path: Optional[str] = None,
        log_to: LogTo = settings.logging.LOG_TO,
    ) -> None:
        """
        Initialize a base logger with console and optional file output.

        Args:
            name (str): Logger name, typically the module/file name (__name__).
            log_path (Optional[str]): Path to the log directory (optional).
        """

        self.logger: logging.Logger = logging.getLogger(name)
        self.handlers: List[logging.Handler] = []

        # Determine log directory
        self.log_path = log_path or settings.logging.LOG_DIRECTORY
        os.makedirs(self.log_path, exist_ok=True)

        # Configure level and format
        log_level = get_log_level(settings.logging.LOG_LEVEL)  # Default is DEBUG
        self.logger.setLevel(log_level)

        # Avoid duplicate handlers if re-instantiated
        if self.logger.handlers:
            self.handlers = self.logger.handlers
            return

        # Formatter setup
        file_formatter = logging.Formatter(
            fmt=settings.logging.LOG_FORMAT,
            datefmt=settings.logging.DATE_FORMAT,
        )
        console_formatter = ColorFormatter(
            fmt=settings.logging.LOG_FORMAT,
            datefmt=settings.logging.DATE_FORMAT,
        )

        match log_to:
            case "CONSOLE":
                # Add console handler only
                self._log_to_console(log_level, console_formatter)
                return
            case "FILE":
                # Add file handler only
                self._log_to_file(file_formatter)
                return
            case "BOTH":
                # Add both handlers
                self._log_to_console(log_level, console_formatter)
                self._log_to_file(file_formatter)
                return

    def _log_to_console(
        self, log_level: int, console_formatter: ColorFormatter
    ) -> None:
        """Sets up console logging handler"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        self.handlers.append(console_handler)

    def _log_to_file(self, file_formatter: logging.Formatter) -> None:
        """Sets up file logging handlers"""
        app_log_path = os.path.join(self.log_path, "app.log")
        file_handler = logging.FileHandler(app_log_path, encoding="utf-8")
        # Allow handler to receive all records but filter later so app.log only
        # contains non-warning/non-error entries (<= INFO).
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        # Attach filter to strip out WARNING and ERROR records from app.log
        file_handler.addFilter(MaxLevelFilter(logging.INFO))
        self.logger.addHandler(file_handler)
        self.handlers.append(file_handler)

        error_log_path = os.path.join(self.log_path, "error.log")
        error_handler = logging.FileHandler(error_log_path, encoding="utf-8")
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(file_formatter)
        self.logger.addHandler(error_handler)
        self.handlers.append(error_handler)

    def debug(self, message: str, **kwargs) -> None:
        """
        Logs detailed debugging information useful during development.

        Use this to trace logic flow, variable states, or diagnose issues
        during development/testing.

        Args:
            message (str): The debug message to log.
            **kwargs: Optional additional context (e.g., input/output data, execution timing).
        """
        self.logger.debug(message, extra=kwargs or None)

    def info(self, message: str, **kwargs) -> None:
        """
        Logs informational messages, such as successful operations or high-level events.

        Use this to track the flow of the application, successful user actions,
        startup sequences, etc.

        Args:
            message (str): The main message to log (human-readable).
            **kwargs: Optional metadata for additional context (e.g., user info, request ID).
        """
        self.logger.info(message, extra=kwargs or None)

    def warning(self, message: str, **kwargs) -> None:
        """
        Logs warning messages, such as deprecated usage, slow responses, or non-critical issues.

        Use this when something unexpected occurred but the app can recover or continue.

        Args:
            message (str): The warning message to log.
            **kwargs: Optional metadata for context (e.g., stack trace, resource info).
        """
        self.logger.warning(message, extra=kwargs or None)

    def error(self, message: str, exception: Optional[Exception] = None, **kwargs) -> None:
        """
        Logs error messages for failed operations or exceptions.

        Use this to capture system failures, unhandled exceptions,
        or application-breaking conditions.

        Args:
            message (str): The error message to log.
            exception (Exception, optional): The exception object, if applicable.
            **kwargs: Optional metadata (e.g., stack trace, context data).
        """
        if exception:
            self.logger.error(
                "%(message)s | Exception: %(exception)s",
                {"message": message, "exception": exception},
                exc_info=True,
                extra=kwargs or None,
            )
        else:
            self.logger.error(message, extra=kwargs or None)

    def critical(self, message: str, exception: Optional[Exception] = None, **kwargs) -> None:
        """
        Logs critical messages for severe errors causing application shutdown.

        Use this for fatal errors that require immediate attention.

        Args:
            message (str): The critical message to log.
            exception (Exception, optional): The exception object, if applicable.
            **kwargs: Optional metadata (e.g., stack trace, context data).
        """
        if exception:
            self.logger.critical(
                "%(message)s | Exception: %(exception)s",
                {"message": message, "exception": exception},
                exc_info=True,
                extra=kwargs or None,
            )
        else:
            self.logger.critical(message, extra=kwargs or None)

    def set_level(self, level: LogLevel) -> None:
        """
        Dynamically change the log level for all attached handlers.

        Args:
            level (LogLevel): New log level (e.g., LogLevel.DEBUG,
                LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR).
        """

        log_level = get_log_level(level)

        self.logger.setLevel(log_level)

        for handler in self.handlers:
            handler.setLevel(log_level)

        self.info(f"Log level updated to {level}")
