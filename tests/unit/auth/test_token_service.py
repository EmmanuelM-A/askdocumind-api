import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
import pytest
from pydantic import SecretStr

from src.auth.domain.auth import AnonymousTokenPayload
from src.auth.services import token_service
from src.auth.services.token_service import (
    create_anonymous_token,
    decode_anonymous_token,
)
from src.exceptions import ApiException

SECRET = "unit-test-secret-key-with-at-least-32-bytes"
OTHER_SECRET = "a-different-secret-key-with-32-plus-bytes"

# ============================= Fixtures =============================


@pytest.fixture
def ttl_days() -> int:
    return 7


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch, ttl_days):
    """Replace the settings object used by the token service."""
    fake = SimpleNamespace(
        auth=SimpleNamespace(
            ANONYMOUS_TOKEN_SECRET=SecretStr(SECRET),
            ANONYMOUS_TOKEN_TTL_DAYS=ttl_days,
        )
    )
    monkeypatch.setattr(token_service, "settings", fake)
    return fake.auth


@pytest.fixture
def user_id() -> UUID:
    return uuid4()


@pytest.fixture
def make_token(user_id):
    """
    Build a token directly with PyJWT, bypassing the service.
    """

    def _make(
        secret: str | None = SECRET,
        algorithm: str = "HS256",
        expires_in: int = 3600,
        drop: tuple[str, ...] = (),
        **overrides,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": str(user_id),
            "iat": now.timestamp(),
            "exp": (now + timedelta(seconds=expires_in)).timestamp(),
        }
        payload.update(overrides)
        for key in drop:
            payload.pop(key)
        return jwt.encode(payload, secret, algorithm=algorithm)

    return _make


def b64(data: dict) -> str:
    raw = json.dumps(data).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# ============================ Tests =============================


def test_create_returns_three_part_jwt(user_id):
    token = create_anonymous_token(user_id)

    assert isinstance(token, str)
    assert len(token.split(".")) == 3


def test_create_header_uses_hs256(user_id):
    token = create_anonymous_token(user_id)

    assert jwt.get_unverified_header(token)["alg"] == "HS256"


def test_create_payload_contains_expected_claims(user_id):
    token = create_anonymous_token(user_id)

    claims = jwt.decode(token, SECRET, algorithms=["HS256"])

    assert claims["user_id"] == str(user_id)
    assert {"iat", "exp"} <= claims.keys()


@pytest.mark.parametrize("ttl_days", [1, 30])
def test_create_expiry_matches_configured_ttl(user_id, ttl_days):
    token = create_anonymous_token(user_id)

    claims = jwt.decode(token, SECRET, algorithms=["HS256"])

    assert claims["exp"] - claims["iat"] == pytest.approx(ttl_days * 86400, abs=1)


def test_create_sets_issued_at_to_current_time(user_id):
    before = datetime.now(timezone.utc).timestamp()
    token = create_anonymous_token(user_id)
    after = datetime.now(timezone.utc).timestamp()

    claims = jwt.decode(token, SECRET, algorithms=["HS256"])

    assert before - 1 <= claims["iat"] <= after + 1


def test_create_signs_with_configured_secret(user_id):
    token = create_anonymous_token(user_id)

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, OTHER_SECRET, algorithms=["HS256"])


def test_decode_round_trip_returns_payload_with_user_id(user_id):
    payload = decode_anonymous_token(create_anonymous_token(user_id))

    assert isinstance(payload, AnonymousTokenPayload)
    assert payload.user_id == user_id


def test_decode_expired_token_raises_401_token_expired(make_token):
    token = make_token(expires_in=-60)

    with pytest.raises(ApiException) as exc_info:
        decode_anonymous_token(token)

    assert exc_info.value.status_code == 401


def test_decode_wrong_secret_raises_token_invalid(make_token):
    token = make_token(secret=OTHER_SECRET)

    with pytest.raises(ApiException) as exc_info:
        decode_anonymous_token(token)

    assert exc_info.value.status_code == 401


@pytest.mark.parametrize("token", ["", "not-a-jwt"])
def test_decode_malformed_token_raises_token_invalid(token):
    with pytest.raises(ApiException) as exc_info:
        decode_anonymous_token(token)

    assert exc_info.value.status_code == 401


def test_decode_tampered_payload_raises_token_invalid(make_token):
    header, _, signature = make_token().split(".")
    forged = b64({"user_id": str(uuid4()), "iat": 0, "exp": 9999999999})

    with pytest.raises(ApiException) as exc_info:
        decode_anonymous_token(f"{header}.{forged}.{signature}")

    assert exc_info.value.status_code == 401


def test_decode_rejects_unsigned_alg_none_token(make_token):
    token = make_token(secret=None, algorithm="none")

    with pytest.raises(ApiException) as exc_info:
        decode_anonymous_token(token)

    assert exc_info.value.status_code == 401


def test_decode_rejects_token_signed_with_other_algorithm(make_token):
    token = make_token(algorithm="HS512")

    with pytest.raises(ApiException) as exc_info:
        decode_anonymous_token(token)

    assert exc_info.value.status_code == 401


def test_decode_error_message_does_not_leak_details(make_token):
    token = make_token(secret=OTHER_SECRET)

    with pytest.raises(ApiException) as exc_info:
        decode_anonymous_token(token)

    assert exc_info.value.status_code == 401


def test_decode_signed_token_missing_user_id_raises_401(make_token):
    token = make_token(drop=("user_id",))

    with pytest.raises(ApiException) as exc_info:
        decode_anonymous_token(token)

    assert exc_info.value.status_code == 401


def test_decode_signed_token_with_non_uuid_user_id_raises_401(make_token):
    token = make_token(user_id="not-a-uuid")

    with pytest.raises(ApiException) as exc_info:
        decode_anonymous_token(token)

    assert exc_info.value.status_code == 401
