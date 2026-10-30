"""
End-to-end tests for GET /v1/chat-session/{chat_session_id}/messages.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.chat_session.domain.chat import ChatMessageRole
from tests.e2e.conftest import cookie_headers

pytestmark = pytest.mark.asyncio

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _url(chat_session_id):
    return f"/v1/chat-session/{chat_session_id}/messages"


def _at(minutes):
    return _BASE_TIME + timedelta(minutes=minutes)


class TestMessages:
    async def test_returns_the_messages_in_the_standard_response(
        self, client, user, make_chat, seed_message
    ):
        chat_id = await make_chat(user.user_id)
        message_id = await seed_message(
            chat_id,
            "What does the report say?",
            _at(0),
            role=ChatMessageRole.USER,
            sources=["report.pdf"],
        )

        response = await client.get(_url(chat_id), headers=user.headers)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == [
            {
                "id": str(message_id),
                "chatSessionId": str(chat_id),
                "role": "user",
                "content": "What does the report say?",
                "sources": ["report.pdf"],
                "createdAt": _at(0).isoformat(),
            }
        ]

    async def test_returns_the_messages_oldest_first(
        self, client, user, make_chat, seed_message
    ):
        chat_id = await make_chat(user.user_id)
        third = await seed_message(chat_id, "third", _at(2))
        first = await seed_message(chat_id, "first", _at(0))
        second = await seed_message(chat_id, "second", _at(1))

        response = await client.get(_url(chat_id), headers=user.headers)

        assert [m["id"] for m in response.json()["data"]] == [
            str(first),
            str(second),
            str(third),
        ]

    async def test_returns_every_role(self, client, user, make_chat, seed_message):
        chat_id = await make_chat(user.user_id)
        for minute, role in enumerate(ChatMessageRole):
            await seed_message(chat_id, role.value, _at(minute), role=role)

        response = await client.get(_url(chat_id), headers=user.headers)

        assert [m["role"] for m in response.json()["data"]] == [
            role.value for role in ChatMessageRole
        ]

    async def test_assistant_message_keeps_all_its_sources(
        self, client, user, make_chat, seed_message
    ):
        chat_id = await make_chat(user.user_id)
        sources = ["a.pdf", "b.txt", "https://example.com/page"]
        await seed_message(
            chat_id, "Answer", _at(0), role=ChatMessageRole.ASSISTANT, sources=sources
        )

        response = await client.get(_url(chat_id), headers=user.headers)

        assert response.json()["data"][0]["sources"] == sources

    async def test_chat_session_without_messages_returns_an_empty_list(
        self, client, user, make_chat
    ):
        chat_id = await make_chat(user.user_id)

        response = await client.get(_url(chat_id), headers=user.headers)

        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_excludes_the_users_other_chat_sessions(
        self, client, user, make_chat, seed_message
    ):
        chat_id = await make_chat(user.user_id)
        other_chat_id = await make_chat(user.user_id)
        wanted = await seed_message(chat_id, "here", _at(0))
        await seed_message(other_chat_id, "elsewhere", _at(0))

        response = await client.get(_url(chat_id), headers=user.headers)

        assert [m["id"] for m in response.json()["data"]] == [str(wanted)]


class TestNotFound:
    async def test_unknown_chat_session_is_not_found(self, client, user):
        response = await client.get(_url(uuid.uuid4()), headers=user.headers)

        assert response.status_code == 404

    async def test_malformed_id_is_rejected(self, client, user):
        response = await client.get(_url("not-a-uuid"), headers=user.headers)

        assert response.status_code == 422


class TestAccess:
    async def test_another_users_chat_session_is_forbidden(
        self, client, user, make_user, make_chat, seed_message
    ):
        chat_id = await make_chat(user.user_id)
        await seed_message(chat_id, "private", _at(0))
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
