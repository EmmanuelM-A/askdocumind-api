"""Helpers for consistent datetime formatting across API and model serialization."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DATETIME_OUTPUT_FORMAT = "%d-%m-%Y %H:%M:%S"
_DISPLAY_TZ = ZoneInfo("Europe/London")


def format_datetime(value: datetime) -> str:
    """Format a datetime as DD-MM-YYYY HH:MM:SS in Europe/London time (BST/GMT)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_DISPLAY_TZ).strftime(DATETIME_OUTPUT_FORMAT)

