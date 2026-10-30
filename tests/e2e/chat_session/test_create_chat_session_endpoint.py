"""
End-to-end tests for POST /v1/chat-session.
"""

import uuid

import pytest

from src.config.configs import settings
from tests.e2e.chat_session.conftest import cookie_headers

pytestmark = pytest.mark.asyncio

_URL = "/v1/chat-session"


class TestCreate:
    async def test_creates_a_chat_session_for_the_cookie_user(
        self, client, user, read_chats
    ):
        response = await client.post(
            _URL, json={"title": "My notes"}, headers=user.headers
        )

        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        [stored] = await read_chats(user.user_id)
        assert body["data"] == {
            "id": str(stored.id),
            "title": "My notes",
            "createdAt": stored.created_at.isoformat(),
        }

    async def test_adds_to_the_users_existing_chat_sessions(
        self, client, user, make_chat, read_chats
    ):
        existing_id = await make_chat(user.user_id)

        response = await client.post(
            _URL, json={"title": "Second"}, headers=user.headers
        )

        assert response.status_code == 201
        stored_ids = {chat.id for chat in await read_chats(user.user_id)}
        assert stored_ids == {existing_id, uuid.UUID(response.json()["data"]["id"])}

    async def test_user_id_in_the_body_is_ignored(
        self, client, user, make_user, read_chats
    ):
        other = await make_user()

        response = await client.post(
            _URL,
            json={"title": "Sneaky", "userId": str(other.user_id)},
            headers=user.headers,
        )

        assert response.status_code == 201
        assert len(await read_chats(user.user_id)) == 1
        assert await read_chats(other.user_id) == []


class TestChatLimit:
    async def test_user_at_the_limit_is_rejected(
        self, client, user, make_chat, read_chats, monkeypatch
    ):
        monkeypatch.setattr(settings.chat_session, "MAX_CHATS_PER_USER", 2)
        await make_chat(user.user_id)
        await make_chat(user.user_id)

        response = await client.post(
            _URL, json={"title": "Third"}, headers=user.headers
        )

        assert response.status_code == 422
        assert len(await read_chats(user.user_id)) == 2

    async def test_user_below_the_limit_can_create_up_to_it(
        self, client, user, make_chat, read_chats, monkeypatch
    ):
        monkeypatch.setattr(settings.chat_session, "MAX_CHATS_PER_USER", 2)
        await make_chat(user.user_id)

        response = await client.post(_URL, json={"title": "Last"}, headers=user.headers)

        assert response.status_code == 201
        assert len(await read_chats(user.user_id)) == 2

    async def test_other_users_chat_sessions_do_not_count(
        self, client, user, make_user, make_chat, monkeypatch
    ):
        monkeypatch.setattr(settings.chat_session, "MAX_CHATS_PER_USER", 1)
        other = await make_user()
        await make_chat(other.user_id)

        response = await client.post(_URL, json={"title": "Mine"}, headers=user.headers)

        assert response.status_code == 201


class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [{}, {"title": None}, {"title": 42}, {"name": "No title"}],
        ids=["empty", "null-title", "number-title", "wrong-field"],
    )
    async def test_invalid_body_is_rejected(self, client, user, read_chats, body):
        response = await client.post(_URL, json=body, headers=user.headers)

        assert response.status_code == 422
        assert await read_chats(user.user_id) == []

    async def test_malformed_json_is_rejected(self, client, user, read_chats):
        response = await client.post(
            _URL,
            content=b'{"title": ',
            headers={**user.headers, "Content-Type": "application/json"},
        )

        assert response.status_code == 422
        assert await read_chats(user.user_id) == []


class TestAccess:
    async def test_missing_cookie_is_unauthorized(self, client):
        response = await client.post(_URL, json={"title": "Anyone"})

        assert response.status_code == 401

    async def test_invalid_token_is_unauthorized(self, client):
        headers = {"Cookie": f"{settings.auth.ANONYMOUS_COOKIE_NAME}=not-a-jwt"}

        response = await client.post(_URL, json={"title": "Anyone"}, headers=headers)

        assert response.status_code == 401

    async def test_token_for_an_unknown_user_is_unauthorized(self, client, read_chats):
        user_id = uuid.uuid4()

        response = await client.post(
            _URL, json={"title": "Ghost"}, headers=cookie_headers(user_id)
        )

        assert response.status_code == 401
        assert await read_chats(user_id) == []
