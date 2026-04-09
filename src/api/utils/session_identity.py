"""
Helpers for anonymous session identity and signed session tokens.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from src.config.configs import settings
from src.errors.custom_exceptions import unauthorized_error, unprocessable_entity_error


@dataclass(frozen=True)
class AnonymousSessionPayload:
    """Decoded anonymous session payload."""

    user_id: UUID
    expires_at: int


class TokenManager:
    """Create and verify signed user tokens."""

    def __init__(self, secret: str, ttl_hours: int) -> None:
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_hours * 60 * 60

    @staticmethod
    def _b64encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

    @staticmethod
    def _b64decode(data: str) -> bytes:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode((data + padding).encode("utf-8"))

    def _sign(self, payload_bytes: bytes) -> str:
        signature = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
        return self._b64encode(signature)

    def create_token(self, user_id: UUID) -> str:
        expires_at = int(time.time()) + self._ttl_seconds
        payload = {"uid": str(user_id), "exp": expires_at}
        payload_bytes = json.dumps(
            payload, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return f"{self._b64encode(payload_bytes)}.{self._sign(payload_bytes)}"

    def decode_token(self, token: str) -> AnonymousSessionPayload:
        try:
            payload_part, signature_part = token.split(".", 1)
            payload_bytes = self._b64decode(payload_part)
            expected_signature = self._sign(payload_bytes)

            if not hmac.compare_digest(expected_signature, signature_part):
                raise ValueError("Invalid user signature.")

            payload = json.loads(payload_bytes.decode("utf-8"))
            user_id = UUID(payload["uid"])
            expires_at = int(payload["exp"])

            if expires_at <= int(time.time()):
                raise ValueError("Anonymous session token has expired.")

            return AnonymousSessionPayload(user_id=user_id, expires_at=expires_at)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise unprocessable_entity_error(
                message="Invalid user signature provided.",
                error_code="INVALID_USER_SIGNATURE",
                stack_trace=str(exc),
            )

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds


_token_manager: TokenManager | None = None


def get_anonymous_session_token_manager() -> TokenManager:
    """Return a singleton anonymous session token manager."""
    global _token_manager

    if _token_manager is None:
        _token_manager = TokenManager(
            secret=settings.auth.USER_SESSION_SECRET.get_secret_value(),
            ttl_hours=settings.auth.USER_SESSION_TTL_HOURS,
        )

    return _token_manager
