"""
Handles the storage and retrieval of the anonymous user ID for the current
request context.
"""

from contextvars import ContextVar, Token
from uuid import UUID

from src.errors.custom_exceptions import unauthorized_error

_anonymous_user_id: ContextVar[UUID | None] = ContextVar(
    "anonymous_user_id", default=None
)


def get_current_anonymous_user_id() -> UUID | None:
    """Return the current anonymous user ID, if one is bound to the request."""
    return _anonymous_user_id.get()


def require_current_anonymous_user_id() -> UUID:
    """Return the current anonymous user ID or raise an authorization error."""
    anonymous_id = get_current_anonymous_user_id()

    if anonymous_id is None:
        raise unauthorized_error(
            message="Anonymous user ID is not set for the current request context.",
            error_code="USER_NOT_AUTHENTICATED",
        )

    return anonymous_id


def set_current_anonymous_user_id(user_id: UUID) -> Token[UUID | None]:
    """Bind the current anonymous user ID to the active request context."""
    return _anonymous_user_id.set(user_id)


def reset_current_anonymous_user_id(token: Token[UUID | None]) -> None:
    """Clear the current anonymous user ID from the active request context."""
    _anonymous_user_id.reset(token)
