"""Rate limiter configuration for the application."""

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.config.configs import settings


def _global_default_limits() -> list[str]:
    return [
        f"{settings.server.RATE_LIMIT_REQUESTS}/{settings.server.RATE_LIMIT_WINDOW}second"
    ]


def user_key_func(request: Request) -> str:
    """Use user ID when present, otherwise fall back to client's IP."""
    user_id = getattr(request.state, "anonymous_user_id", None)

    if user_id is not None:
        return f"anon:{user_id}"

    return get_remote_address(request)


def chat_query_limit() -> str:
    """Per-anonymous-session chat request limit expression for SlowAPI."""
    return f"{settings.server.MAX_CHAT_QUERIES_PER_MINUTE}/minute"


def upload_limit() -> str:
    """Per-anonymous-session document upload limit expression for SlowAPI."""
    return f"{settings.server.MAX_UPLOAD_REQUESTS_PER_MINUTE}/minute"


def session_limit() -> str:
    """Per-anonymous-session chat session mutation limit expression for SlowAPI."""
    return f"{settings.server.MAX_SESSION_REQUESTS_PER_MINUTE}/minute"


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=_global_default_limits(),  # type: ignore[arg-type]
    enabled=True,  # Enable rate limiting by default
)
