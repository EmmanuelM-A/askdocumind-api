"""
End-to-end tests for DELETE /api/sessions/{session_id}. No dependency is
mocked anywhere in this file.
"""

from uuid import uuid4

from src.config.configs import settings

ENDPOINT = "/api/sessions"
COOKIE_NAME = settings.auth.COOKIE_NAME


def _url(session_id) -> str:
    return f"{ENDPOINT}/{session_id}"


# ============================ Happy path ============================


async def test_delete_returns_200_with_chat_id(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.delete(_url(chat_id), cookies=auth_cookie(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Chat session deleted successfully."
    assert body["data"]["chat_id"] == str(chat_id)


async def test_delete_actually_removes_row_from_db(
    app_client, seed_user, seed_chat_session, auth_cookie, chat_session_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    app_client.delete(_url(chat_id), cookies=auth_cookie(user_id))

    stored = await chat_session_repo.get_by_id(chat_id)
    assert stored is None


async def test_delete_does_not_affect_other_sessions(
    app_client, seed_user, seed_chat_session, auth_cookie, chat_session_repo
):
    user_a = await seed_user()
    user_b = await seed_user()
    chat_a = await seed_chat_session(user_a, title="A's chat")
    chat_b = await seed_chat_session(user_b, title="B's chat")

    app_client.delete(_url(chat_a), cookies=auth_cookie(user_a))

    assert await chat_session_repo.get_by_id(chat_a) is None
    assert await chat_session_repo.get_by_id(chat_b) is not None


# ==================== Not found / ownership ====================


async def test_delete_nonexistent_session_returns_404(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.delete(_url(uuid4()), cookies=auth_cookie(user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


async def test_delete_session_owned_by_another_user_returns_404_and_is_not_deleted(
    app_client, seed_user, seed_chat_session, auth_cookie, chat_session_repo
):
    owner_id = await seed_user()
    other_user_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)

    response = app_client.delete(_url(chat_id), cookies=auth_cookie(other_user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"
    assert await chat_session_repo.get_by_id(chat_id) is not None


async def test_delete_twice_returns_404_on_second_call(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    cookies = auth_cookie(user_id)

    first = app_client.delete(_url(chat_id), cookies=cookies)
    second = app_client.delete(_url(chat_id), cookies=cookies)

    assert first.status_code == 200
    assert second.status_code == 404
    assert second.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


# ==================== Invalid path parameter ====================


async def test_delete_invalid_uuid_path_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.delete(_url("not-a-uuid"), cookies=auth_cookie(user_id))

    assert response.status_code == 422
    assert "detail" in response.json()


# ==================== Auth failure matrix ====================


async def test_delete_no_cookie_returns_422(app_client, seed_user, seed_chat_session):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.delete(_url(chat_id))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_COOKIE_VALUE"


async def test_delete_garbage_cookie_returns_422(app_client, seed_user, seed_chat_session):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.delete(_url(chat_id), cookies={COOKIE_NAME: "garbage"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_delete_valid_signature_nonexistent_user_returns_404(
    app_client, token_manager, seed_user, seed_chat_session
):
    owner_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)
    cookie_token = token_manager.create_token(uuid4())

    response = app_client.delete(_url(chat_id), cookies={COOKIE_NAME: cookie_token})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANONYMOUS_USER_NOT_FOUND"


# ==================== HTTP-layer edges ====================


async def test_delete_get_method_not_allowed_on_wrong_verb(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    """PUT isn't a registered method for this path, so it should 405."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.put(_url(chat_id), cookies=auth_cookie(user_id))

    assert response.status_code == 405
