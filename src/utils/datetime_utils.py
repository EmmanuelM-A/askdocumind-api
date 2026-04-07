"""Helpers for consistent datetime formatting across API and model serialization."""

from datetime import datetime, timezone

DATETIME_OUTPUT_FORMAT = "%Y-%m-%d %H:%M:%S"


def format_datetime(value: datetime) -> str:
    """Format datetimes to a consistent UTC string representation."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.strftime(DATETIME_OUTPUT_FORMAT)

