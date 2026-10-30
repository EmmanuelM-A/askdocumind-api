"""
End-to-end tests for DELETE /v1/chat-session/{chat_session_id}.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.exceptions import object_storage_error
from tests.e2e.conftest import cookie_headers

pytestmark = pytest.mark.asyncio

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _url(chat_session_id):
    return f"/v1/chat-session/{chat_session_id}"


def _all_rows_exist(rows):
    return all(count > 0 for count in rows.values())


def _no_rows_exist(rows):
    return all(count == 0 for count in rows.values())


@pytest.fixture
def full_chat(make_chat, seed_message, seed_document):
    """Commit a chat session with a message, a document, an embedding and a file."""

    async def _make(user_id):
        chat_id = await make_chat(user_id)
        await seed_message(chat_id, "hello", _BASE_TIME)
        object_key = await seed_document(chat_id)
        return chat_id, object_key

    return _make


class TestDelete:
    async def test_removes_the_chat_session_its_rows_and_its_files(
        self, client, user, full_chat, count_rows, object_storage
    ):
        chat_id, object_key = await full_chat(user.user_id)

        response = await client.delete(_url(chat_id), headers=user.headers)

        assert response.status_code == 204
        assert response.content == b""
        assert _no_rows_exist(await count_rows(chat_id))
        assert object_storage.exists(object_key) is False

    async def test_removes_every_document_in_the_chat_session(
        self, client, user, make_chat, seed_document, count_rows, object_storage
    ):
        chat_id = await make_chat(user.user_id)
        keys = [await seed_document(chat_id) for _ in range(3)]

        await client.delete(_url(chat_id), headers=user.headers)

        assert _no_rows_exist(await count_rows(chat_id))
        assert not any(object_storage.exists(key) for key in keys)

    async def test_empty_chat_session_is_deleted(
        self, client, user, make_chat, read_chats
    ):
        chat_id = await make_chat(user.user_id)

        response = await client.delete(_url(chat_id), headers=user.headers)

        assert response.status_code == 204
        assert await read_chats(user.user_id) == []

    async def test_leaves_the_users_other_chat_sessions_alone(
        self, client, user, full_chat, count_rows, object_storage
    ):
        doomed_id, _ = await full_chat(user.user_id)
        kept_id, kept_key = await full_chat(user.user_id)

        await client.delete(_url(doomed_id), headers=user.headers)

        assert _all_rows_exist(await count_rows(kept_id))
        assert object_storage.exists(kept_key) is True

    async def test_keeps_the_user(self, client, user, make_chat):
        chat_id = await make_chat(user.user_id)
        await client.delete(_url(chat_id), headers=user.headers)

        response = await client.post(
            "/v1/chat-session", json={"title": "Next"}, headers=user.headers
        )

        assert response.status_code == 201


class TestNotFound:
    async def test_unknown_chat_session_is_not_found(self, client, user):
        response = await client.delete(_url(uuid.uuid4()), headers=user.headers)

        assert response.status_code == 404

    async def test_second_delete_is_not_found(self, client, user, make_chat):
        chat_id = await make_chat(user.user_id)
        await client.delete(_url(chat_id), headers=user.headers)

        response = await client.delete(_url(chat_id), headers=user.headers)

        assert response.status_code == 404

    async def test_malformed_id_is_rejected(self, client, user):
        response = await client.delete(_url("not-a-uuid"), headers=user.headers)

        assert response.status_code == 422


class TestAccess:
    async def test_another_users_chat_session_is_forbidden_and_kept(
        self, client, user, make_user, full_chat, count_rows, object_storage
    ):
        chat_id, object_key = await full_chat(user.user_id)
        intruder = await make_user()

        response = await client.delete(_url(chat_id), headers=intruder.headers)

        assert response.status_code == 403
        assert _all_rows_exist(await count_rows(chat_id))
        assert object_storage.exists(object_key) is True

    async def test_missing_cookie_is_unauthorized_and_kept(
        self, client, user, full_chat, count_rows
    ):
        chat_id, _ = await full_chat(user.user_id)

        response = await client.delete(_url(chat_id))

        assert response.status_code == 401
        assert _all_rows_exist(await count_rows(chat_id))

    async def test_token_for_an_unknown_user_is_unauthorized_and_kept(
        self, client, user, full_chat, count_rows
    ):
        chat_id, _ = await full_chat(user.user_id)

        response = await client.delete(
            _url(chat_id), headers=cookie_headers(uuid.uuid4())
        )

        assert response.status_code == 401
        assert _all_rows_exist(await count_rows(chat_id))


class TestStorageFailure:
    async def test_storage_failure_returns_500_and_keeps_everything(
        self, client, user, full_chat, count_rows, object_storage
    ):
        chat_id, object_key = await full_chat(user.user_id)
        failure = object_storage_error(message="S3 is down")

        with patch.object(object_storage, "delete_prefix", side_effect=failure):
            response = await client.delete(_url(chat_id), headers=user.headers)

        assert response.status_code == 500
        assert _all_rows_exist(await count_rows(chat_id))
        assert object_storage.exists(object_key) is True

    async def test_delete_can_be_retried_after_a_storage_failure(
        self, client, user, full_chat, count_rows, object_storage
    ):
        chat_id, object_key = await full_chat(user.user_id)
        failure = object_storage_error(message="S3 is down")
        with patch.object(object_storage, "delete_prefix", side_effect=failure):
            await client.delete(_url(chat_id), headers=user.headers)

        response = await client.delete(_url(chat_id), headers=user.headers)

        assert response.status_code == 204
        assert _no_rows_exist(await count_rows(chat_id))
        assert object_storage.exists(object_key) is False
