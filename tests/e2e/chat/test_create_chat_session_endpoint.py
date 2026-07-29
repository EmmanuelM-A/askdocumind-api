"""
End-to-end tests for POST /api/sessions (create chat session). No dependency
is mocked anywhere in this file - every test hits the real FastAPI app, the
real database, the real auth middleware, and the real rate limiter.
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from src.config.configs import settings

ENDPOINT = "/api/sessions"
COOKIE_NAME = settings.auth.COOKIE_NAME


# ============================ Happy path ============================


async def test_create_returns_201_with_chat_id(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT, json={"title": "My First Chat"}, cookies=auth_cookie(user_id)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Chat session created successfully."
    UUID(body["data"]["chat_id"])  # does not raise


async def test_create_persists_row_with_correct_title_and_owner(
    app_client, seed_user, auth_cookie, chat_session_repo
):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT, json={"title": "Persisted Chat"}, cookies=auth_cookie(user_id)
    )
    chat_id = UUID(response.json()["data"]["chat_id"])

    stored = await chat_session_repo.get_by_id(chat_id)

    assert stored is not None
    assert stored.title == "Persisted Chat"
    assert stored.user_id == user_id
    assert stored.created_at is not None


async def test_create_response_does_not_leak_internal_fields(
    app_client, seed_user, auth_cookie
):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT, json={"title": "Chat"}, cookies=auth_cookie(user_id)
    )
    body = response.json()

    assert set(body.keys()) == {"success", "timestamp", "message", "data"}
    assert set(body["data"].keys()) == {"chat_id"}


async def test_create_timestamp_field_is_recent(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT, json={"title": "Chat"}, cookies=auth_cookie(user_id)
    )
    raw_timestamp = response.json()["timestamp"]

    parsed = datetime.strptime(raw_timestamp, "%d-%m-%Y %H:%M:%S").replace(
        tzinfo=ZoneInfo("Europe/London")
    )
    delta = abs((datetime.now(timezone.utc) - parsed).total_seconds())
    assert delta < 10


async def test_create_two_different_users_can_each_create_their_own_session(
    app_client, seed_user, auth_cookie
):
    user_a = await seed_user()
    user_b = await seed_user()

    response_a = app_client.post(
        ENDPOINT, json={"title": "A's chat"}, cookies=auth_cookie(user_a)
    )
    response_b = app_client.post(
        ENDPOINT, json={"title": "B's chat"}, cookies=auth_cookie(user_b)
    )

    assert response_a.status_code == 201
    assert response_b.status_code == 201
    assert response_a.json()["data"]["chat_id"] != response_b.json()["data"]["chat_id"]


# ==================== MAX_CHATS_PER_USER (defaults to 1) ====================


async def test_create_second_session_for_same_user_hits_max_chats_limit(
    app_client, seed_user, auth_cookie
):
    user_id = await seed_user()
    cookies = auth_cookie(user_id)

    first = app_client.post(ENDPOINT, json={"title": "Chat 1"}, cookies=cookies)
    assert first.status_code == 201

    second = app_client.post(ENDPOINT, json={"title": "Chat 2"}, cookies=cookies)

    assert second.status_code == 422
    body = second.json()
    assert body["success"] is False
    assert body["error"]["code"] == "MAX_CHATS_PER_USER_REACHED"


# ==================== Auth failure matrix ====================


async def test_create_no_cookie_returns_422(app_client):
    response = app_client.post(ENDPOINT, json={"title": "Chat"})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NO_COOKIE_VALUE"


async def test_create_garbage_cookie_returns_422(app_client):
    response = app_client.post(
        ENDPOINT, json={"title": "Chat"}, cookies={COOKIE_NAME: "not-a-real-token"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_create_tampered_signature_cookie_returns_422(
    app_client, token_manager, seed_user
):
    user_id = await seed_user()
    valid_token = token_manager.create_token(user_id)
    payload_part, signature_part = valid_token.split(".", 1)
    tampered_signature = (
        signature_part[::-1] if signature_part[::-1] != signature_part else signature_part + "x"
    )
    tampered_token = f"{payload_part}.{tampered_signature}"

    response = app_client.post(
        ENDPOINT, json={"title": "Chat"}, cookies={COOKIE_NAME: tampered_token}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_create_expired_cookie_returns_422(app_client, seed_user):
    from src.api.utils.session_manager import TokenManager

    user_id = await seed_user()
    short_lived_manager = TokenManager(
        secret=settings.auth.USER_SESSION_SECRET.get_secret_value(),
        ttl_hours=1 / 3600,  # 1 second
    )
    expiring_token = short_lived_manager.create_token(user_id)
    await asyncio.sleep(1.1)

    response = app_client.post(
        ENDPOINT, json={"title": "Chat"}, cookies={COOKIE_NAME: expiring_token}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_create_valid_signature_nonexistent_user_returns_404(
    app_client, token_manager
):
    random_user_id = uuid4()
    cookie_token = token_manager.create_token(random_user_id)

    response = app_client.post(
        ENDPOINT, json={"title": "Chat"}, cookies={COOKIE_NAME: cookie_token}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANONYMOUS_USER_NOT_FOUND"


# ==================== Validation ====================


async def test_create_missing_title_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(ENDPOINT, json={}, cookies=auth_cookie(user_id))

    assert response.status_code == 422


async def test_create_empty_title_is_accepted(app_client, seed_user, auth_cookie):
    """title has no length/whitespace constraint in CreateChatSessionData -
    an empty string is a valid (if unusual) value."""
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT, json={"title": ""}, cookies=auth_cookie(user_id)
    )

    assert response.status_code == 201
    assert response.json()["data"]["chat_id"] is not None


async def test_create_non_string_title_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT, json={"title": 12345}, cookies=auth_cookie(user_id)
    )

    assert response.status_code == 422


async def test_create_extra_unexpected_fields_are_ignored(
    app_client, seed_user, auth_cookie
):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT,
        json={"title": "Chat", "unexpected_field": "should be ignored"},
        cookies=auth_cookie(user_id),
    )

    assert response.status_code == 201


# ==================== HTTP-layer edges ====================


async def test_create_get_method_not_allowed(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.get(ENDPOINT, cookies=auth_cookie(user_id))

    assert response.status_code == 405


async def test_create_trailing_slash_returns_404(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        f"{ENDPOINT}/", json={"title": "Chat"}, cookies=auth_cookie(user_id), follow_redirects=False
    )

    assert response.status_code == 404
