from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """Return the current UTC time as a naive datetime for TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
