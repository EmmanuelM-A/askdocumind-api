"""
End-to-end tests for GET /api/sessions/{session_id}/messages. No dependency
is mocked anywhere in this file.
"""

from uuid import uuid4

from src.config.configs import settings
from src.config.constants import ChatMessageRole
from src.database.models import ChatMessage

ENDPOINT = "/api/sessions"
COOKIE_NAME = settings.auth.COOKIE_NAME


def _url(session_id) -> str:
    return f"{ENDPOINT}/{session_id}/messages"


# ============================ Happy path ============================


async def test_get_messages_empty_session_returns_empty_list(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.get(_url(chat_id), cookies=auth_cookie(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Chat messages fetched successfully."
    assert body["data"] == []


async def test_get_messages_returns_seeded_messages_with_correct_shape(
    app_client, seed_user, seed_chat_session, auth_cookie, chat_message_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    await chat_message_repo.create(
        ChatMessage(session_id=chat_id, role=ChatMessageRole.USER, content="Hello")
    )
    await chat_message_repo.create(
        ChatMessage(
            session_id=chat_id, role=ChatMessageRole.ASSISTANT, content="Hi there"
        )
    )

    response = app_client.get(_url(chat_id), cookies=auth_cookie(user_id))

    assert response.status_code == 200
    messages = response.json()["data"]
    assert len(messages) == 2
    contents = {m["content"] for m in messages}
    assert contents == {"Hello", "Hi there"}
    for message in messages:
        assert set(message.keys()) == {
            "id",
            "session_id",
            "role",
            "content",
            "sources",
            "created_at",
        }
        assert message["session_id"] == str(chat_id)


async def test_get_messages_only_returns_messages_for_requested_session(
    app_client, seed_user, seed_chat_session, auth_cookie, chat_message_repo
):
    user_id = await seed_user()
    chat_id_a = await seed_chat_session(user_id, title="Chat A")
    await chat_message_repo.create(
        ChatMessage(session_id=chat_id_a, role=ChatMessageRole.USER, content="In A")
    )

    response = app_client.get(_url(chat_id_a), cookies=auth_cookie(user_id))

    messages = response.json()["data"]
    assert len(messages) == 1
    assert messages[0]["content"] == "In A"


# ==================== Not found / ownership ====================


async def test_get_messages_nonexistent_session_returns_404(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.get(_url(uuid4()), cookies=auth_cookie(user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


async def test_get_messages_session_owned_by_another_user_returns_404(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    owner_id = await seed_user()
    other_user_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)

    response = app_client.get(_url(chat_id), cookies=auth_cookie(other_user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


# ==================== Invalid path parameter ====================


async def test_get_messages_invalid_uuid_path_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.get(_url("not-a-uuid"), cookies=auth_cookie(user_id))

    assert response.status_code == 422
    assert "detail" in response.json()


# ==================== Auth failure matrix ====================


async def test_get_messages_no_cookie_returns_422(app_client, seed_user, seed_chat_session):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.get(_url(chat_id))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_COOKIE_VALUE"


async def test_get_messages_garbage_cookie_returns_422(
    app_client, seed_user, seed_chat_session
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.get(_url(chat_id), cookies={COOKIE_NAME: "garbage"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_get_messages_valid_signature_nonexistent_user_returns_404(
    app_client, token_manager, seed_user, seed_chat_session
):
    owner_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)
    cookie_token = token_manager.create_token(uuid4())

    response = app_client.get(_url(chat_id), cookies={COOKIE_NAME: cookie_token})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANONYMOUS_USER_NOT_FOUND"


# ==================== HTTP-layer edges ====================


async def test_get_messages_delete_method_not_allowed(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.delete(_url(chat_id), cookies=auth_cookie(user_id))

    assert response.status_code == 405
