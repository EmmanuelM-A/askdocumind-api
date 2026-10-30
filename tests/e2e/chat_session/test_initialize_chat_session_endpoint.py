"""
End-to-end tests for POST /v1/chat-session/init.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.config.configs import settings
from tests.e2e.conftest import cookie_headers

pytestmark = pytest.mark.asyncio

_URL = "/v1/chat-session/init"
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


class TestInitialize:
    async def test_creates_a_chat_session_when_the_user_has_none(
        self, client, user, read_chats
    ):
        response = await client.post(
            _URL, json={"title": "Welcome"}, headers=user.headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        [stored] = await read_chats(user.user_id)
        assert body["data"] == {
            "id": str(stored.id),
            "title": "Welcome",
            "createdAt": stored.created_at.isoformat(),
        }

    async def test_returns_the_latest_chat_session_without_creating_one(
        self, client, user, make_chat, read_chats
    ):
        await make_chat(user.user_id, title="older", created_at=_BASE_TIME)
        latest_id = await make_chat(
            user.user_id, title="latest", created_at=_BASE_TIME + timedelta(hours=1)
        )

        response = await client.post(
            _URL, json={"title": "Unused"}, headers=user.headers
        )

        assert response.status_code == 200
        assert response.json()["data"]["id"] == str(latest_id)
        assert response.json()["data"]["title"] == "latest"
        assert len(await read_chats(user.user_id)) == 2

    async def test_repeated_calls_return_the_same_chat_session(
        self, client, user, read_chats
    ):
        first = await client.post(_URL, json={"title": "Once"}, headers=user.headers)
        second = await client.post(_URL, json={"title": "Twice"}, headers=user.headers)

        assert first.json()["data"]["id"] == second.json()["data"]["id"]
        assert second.json()["data"]["title"] == "Once"
        assert len(await read_chats(user.user_id)) == 1

    async def test_ignores_other_users_chat_sessions(
        self, client, user, make_user, make_chat, read_chats
    ):
        other = await make_user()
        others_chat_id = await make_chat(other.user_id)

        response = await client.post(_URL, json={"title": "Mine"}, headers=user.headers)

        assert response.status_code == 200
        assert response.json()["data"]["id"] != str(others_chat_id)
        assert len(await read_chats(user.user_id)) == 1

    async def test_existing_chat_session_is_returned_at_the_chat_limit(
        self, client, user, make_chat, monkeypatch
    ):
        monkeypatch.setattr(settings.chat_session, "MAX_CHATS_PER_USER", 1)
        chat_id = await make_chat(user.user_id)

        response = await client.post(
            _URL, json={"title": "Again"}, headers=user.headers
        )

        assert response.status_code == 200
        assert response.json()["data"]["id"] == str(chat_id)


class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [{}, {"title": None}, {"title": 42}],
        ids=["empty", "null-title", "number-title"],
    )
    async def test_invalid_body_is_rejected(self, client, user, read_chats, body):
        response = await client.post(_URL, json=body, headers=user.headers)

        assert response.status_code == 422
        assert await read_chats(user.user_id) == []

    async def test_invalid_body_is_rejected_even_with_an_existing_chat_session(
        self, client, user, make_chat
    ):
        await make_chat(user.user_id)

        response = await client.post(_URL, json={}, headers=user.headers)

        assert response.status_code == 422


class TestAccess:
    async def test_missing_cookie_is_unauthorized(self, client):
        response = await client.post(_URL, json={"title": "Anyone"})

        assert response.status_code == 401

    async def test_token_for_an_unknown_user_is_unauthorized(self, client, read_chats):
        user_id = uuid.uuid4()

        response = await client.post(
            _URL, json={"title": "Ghost"}, headers=cookie_headers(user_id)
        )

        assert response.status_code == 401
        assert await read_chats(user_id) == []
