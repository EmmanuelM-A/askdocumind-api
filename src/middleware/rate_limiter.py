"""Rate limiter configuration for the application."""

import math
import time

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.config.configs import settings
from src.response.delivery import send_error_response

DEFAULT_LIMIT = (
    f"{settings.server.RATE_LIMIT_REQUESTS}/"
    f"{settings.server.RATE_LIMIT_WINDOW_SECS}second"
)


def user_key_func(request: Request) -> str:
    """
    Key by user ID when present, otherwise by client IP.
    """
    if hasattr(request.state, "user_id"):
        return f"anon:{request.state.user_id}"

    return get_remote_address(request)


limiter = Limiter(
    key_func=user_key_func,
    default_limits=[DEFAULT_LIMIT],
    enabled=settings.server.RATE_LIMIT_ENABLED,
    storage_uri=settings.server.RATE_LIMIT_STORAGE_URI,
)

# NOTE: SlowAPI's middleware cannot find routes inside included routers, so
# NOTE: default_limits never reach them. Every API route needs a decorator.
default_limit = limiter.limit(DEFAULT_LIMIT)
health_server_limit = limiter.limit(settings.server.RATE_LIMIT_HEALTH_SERVER)
health_db_limit = limiter.limit(settings.server.RATE_LIMIT_HEALTH_DB)

# Routes in a group share one budget per client
chat_session_limit = limiter.shared_limit(
    settings.server.RATE_LIMIT_CHAT_SESSION, scope="chat-session"
)
uploads_limit = limiter.shared_limit(
    settings.server.RATE_LIMIT_UPLOADS, scope="uploads"
)
chatbot_limit = limiter.shared_limit(
    settings.server.RATE_LIMIT_CHATBOT, scope="chatbot"
)


def _retry_after_secs(request: Request) -> int:
    limit, args = request.state.view_rate_limit
    reset_at, _ = limiter.limiter.get_window_stats(limit, *args)
    return max(1, math.ceil(reset_at - time.time()))


def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """
    Return the standard error response with a Retry-After header.
    """
    return send_error_response(
        message=f"Rate limit exceeded: {exc.detail}. Please try again later.",
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        error_code="RATE_LIMIT_EXCEEDED",
        headers={"Retry-After": str(_retry_after_secs(request))},
    )
