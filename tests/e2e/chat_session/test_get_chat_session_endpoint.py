"""
End-to-end tests for GET /v1/chat-session/{chat_session_id}.
"""

import uuid

import pytest
from limits import parse

from src.config.configs import settings
from tests.e2e.conftest import cookie_headers

pytestmark = pytest.mark.asyncio

# Shared by every chat session endpoint
_RATE_LIMIT = parse(settings.server.RATE_LIMIT_CHAT_SESSION).amount


def _url(chat_session_id):
    return f"/v1/chat-session/{chat_session_id}"


class TestGet:
    async def test_returns_the_chat_session(self, client, user, make_chat, read_chats):
        chat_id = await make_chat(user.user_id, title="Research")

        response = await client.get(_url(chat_id), headers=user.headers)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        [stored] = await read_chats(user.user_id)
        assert body["data"] == {
            "id": str(chat_id),
            "title": "Research",
            "createdAt": stored.created_at.isoformat(),
        }

    async def test_returns_the_requested_chat_session_of_several(
        self, client, user, make_chat
    ):
        await make_chat(user.user_id, title="first")
        wanted = await make_chat(user.user_id, title="second")
        await make_chat(user.user_id, title="third")

        response = await client.get(_url(wanted), headers=user.headers)

        assert response.json()["data"]["title"] == "second"

    async def test_does_not_change_the_chat_session(
        self, client, user, make_chat, read_chats
    ):
        chat_id = await make_chat(user.user_id, title="Unchanged")
        [before] = await read_chats(user.user_id)

        await client.get(_url(chat_id), headers=user.headers)

        [after] = await read_chats(user.user_id)
        assert (after.title, after.created_at) == (before.title, before.created_at)


class TestNotFound:
    async def test_unknown_chat_session_is_not_found(self, client, user):
        response = await client.get(_url(uuid.uuid4()), headers=user.headers)

        assert response.status_code == 404

    async def test_deleted_chat_session_is_not_found(self, client, user, make_chat):
        chat_id = await make_chat(user.user_id)
        await client.delete(_url(chat_id), headers=user.headers)

        response = await client.get(_url(chat_id), headers=user.headers)

        assert response.status_code == 404

    async def test_malformed_id_is_rejected(self, client, user):
        response = await client.get(_url("not-a-uuid"), headers=user.headers)

        assert response.status_code == 422


class TestAccess:
    async def test_another_users_chat_session_is_forbidden(
        self, client, user, make_user, make_chat
    ):
        chat_id = await make_chat(user.user_id)
        intruder = await make_user()

        response = await client.get(_url(chat_id), headers=intruder.headers)

        assert response.status_code == 403

    async def test_missing_cookie_is_unauthorized(self, client, user, make_chat):
        chat_id = await make_chat(user.user_id)

        response = await client.get(_url(chat_id))

        assert response.status_code == 401

    async def test_token_for_an_unknown_user_is_unauthorized(
        self, client, user, make_chat
    ):
        chat_id = await make_chat(user.user_id)

        response = await client.get(_url(chat_id), headers=cookie_headers(uuid.uuid4()))

        assert response.status_code == 401


class TestRateLimit:
    async def test_requests_over_the_limit_are_rejected(self, client, user, make_chat):
        chat_id = await make_chat(user.user_id)
        for _ in range(_RATE_LIMIT):
            assert (
                await client.get(_url(chat_id), headers=user.headers)
            ).status_code == 200

        response = await client.get(_url(chat_id), headers=user.headers)

        assert response.status_code == 429

    async def test_limit_is_shared_with_the_other_chat_session_endpoints(
        self, client, user, make_chat
    ):
        chat_id = await make_chat(user.user_id)
        for _ in range(_RATE_LIMIT):
            await client.get(_url(chat_id), headers=user.headers)

        response = await client.get(f"{_url(chat_id)}/messages", headers=user.headers)

        assert response.status_code == 429

    async def test_limit_is_counted_per_user(self, client, user, make_user, make_chat):
        chat_id = await make_chat(user.user_id)
        for _ in range(_RATE_LIMIT):
            await client.get(_url(chat_id), headers=user.headers)
        other = await make_user()
        other_chat_id = await make_chat(other.user_id)

        response = await client.get(_url(other_chat_id), headers=other.headers)

        assert response.status_code == 200
