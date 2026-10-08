from datetime import datetime, timezone, timedelta
from uuid import UUID

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from src.auth.domain.auth import AnonymousTokenPayload
from src.config.configs import settings
from src.exceptions import unauthorized_error


def create_anonymous_token(user_id: UUID) -> str:
    """
    Generate a JWT token for an anonymous user.
    """
    now = datetime.now(timezone.utc)

    payload = AnonymousTokenPayload(
        user_id=user_id,
        iat=now.timestamp(),
        exp=(now + timedelta(days=settings.auth.ANONYMOUS_TOKEN_TTL_DAYS)).timestamp(),
    )

    return jwt.encode(
        payload.to_dict(),
        key=settings.auth.ANONYMOUS_TOKEN_SECRET.get_secret_value(),
        algorithm="HS256",
    )


def decode_anonymous_token(token: str) -> AnonymousTokenPayload:
    """
    Verify a JWT token for an anonymous user.
    """
    try:
        payload = jwt.decode(
            token,
            key=settings.auth.ANONYMOUS_TOKEN_SECRET.get_secret_value(),
            algorithms=["HS256"],
        )
        return AnonymousTokenPayload(**payload)
    except ExpiredSignatureError:
        raise unauthorized_error(
            message="Invalid token provided", error_code="TOKEN_EXPIRED"
        )
    except InvalidTokenError:
        raise unauthorized_error(
            message="Invalid token provided", error_code="TOKEN_INVALID"
        )
