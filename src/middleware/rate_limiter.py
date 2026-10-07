"""Rate limiter configuration for the application."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.config.configs import settings

DEFAULT_LIMIT = (
    f"{settings.server.RATE_LIMIT_REQUESTS}/"
    f"{settings.server.RATE_LIMIT_WINDOW_SECS}second"
)
HEALTH_API_LIMIT = "60/minute"
HEALTH_DB_LIMIT = "30/minute"


def user_key_func(request: Request) -> str:
    """
    Key by anonymous user ID when present, otherwise by client IP.
    """
    if hasattr(request.state, "anonymous_user_id"):
        return f"anon:{request.state.anonymous_user_id}"

    return get_remote_address(request)


limiter = Limiter(
    key_func=user_key_func,
    default_limits=[DEFAULT_LIMIT],
    enabled=settings.server.RATE_LIMIT_ENABLED,
)
