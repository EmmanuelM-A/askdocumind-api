"""
End-to-end tests for GET /api/sessions/{session_id} (get chat session
metadata). No dependency is mocked anywhere in this file.

Also serves as the regression check for the total_messages bugfix: prior to
removing the dead `self.total_messages` reference from `ChatSession.to_dict()`
/ `__repr__`, every one of these happy-path calls crashed with a 500.
"""

from uuid import uuid4

from src.config.configs import settings

ENDPOINT = "/api/sessions"
COOKIE_NAME = settings.auth.COOKIE_NAME


def _url(session_id) -> str:
    return f"{ENDPOINT}/{session_id}"


# ============================ Happy path ============================


async def test_get_returns_200_with_session_metadata(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id, title="My Chat")

    response = app_client.get(_url(chat_id), cookies=auth_cookie(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Chat session fetched successfully."
    assert body["data"]["id"] == str(chat_id)
    assert body["data"]["title"] == "My Chat"
    assert "created_at" in body["data"]


async def test_get_response_data_has_no_leftover_total_messages_field(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    """Regression check for the total_messages bugfix: the response shape
    should only contain id/title/created_at."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.get(_url(chat_id), cookies=auth_cookie(user_id))

    assert set(response.json()["data"].keys()) == {"id", "title", "created_at"}


async def test_get_response_does_not_leak_top_level_internal_fields(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.get(_url(chat_id), cookies=auth_cookie(user_id))

    assert set(response.json().keys()) == {"success", "timestamp", "message", "data"}


# ==================== Not found / ownership ====================


async def test_get_nonexistent_session_returns_404(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.get(_url(uuid4()), cookies=auth_cookie(user_id))

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


async def test_get_session_owned_by_another_user_returns_404_not_403(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    """Ownership check is fused with existence: querying by id+user_id
    together means a wrong-owner request looks identical to not-found."""
    owner_id = await seed_user()
    other_user_id = await seed_user()
    chat_id = await seed_chat_session(owner_id, title="Owner's chat")

    response = app_client.get(_url(chat_id), cookies=auth_cookie(other_user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


async def test_get_deleted_session_returns_404(
    app_client, seed_user, seed_chat_session, auth_cookie, chat_session_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    await chat_session_repo.delete(chat_id)

    response = app_client.get(_url(chat_id), cookies=auth_cookie(user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


# ==================== Invalid path parameter ====================


async def test_get_invalid_uuid_path_returns_422_with_default_fastapi_shape(
    app_client, seed_user, auth_cookie
):
    """Non-UUID path segments are rejected by FastAPI's own validation layer
    before the route body runs, so the error body uses FastAPI's default
    {"detail": [...]} shape rather than the app's {"success": False, ...}
    ErrorResponseModel shape used everywhere else."""
    user_id = await seed_user()

    response = app_client.get(_url("not-a-uuid"), cookies=auth_cookie(user_id))

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert "success" not in body


# ==================== Auth failure matrix ====================


async def test_get_no_cookie_returns_422(app_client, seed_user, seed_chat_session):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.get(_url(chat_id))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_COOKIE_VALUE"


async def test_get_garbage_cookie_returns_422(app_client, seed_user, seed_chat_session):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.get(_url(chat_id), cookies={COOKIE_NAME: "garbage"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_get_valid_signature_nonexistent_user_returns_404(
    app_client, token_manager, seed_user, seed_chat_session
):
    owner_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)
    cookie_token = token_manager.create_token(uuid4())

    response = app_client.get(_url(chat_id), cookies={COOKIE_NAME: cookie_token})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANONYMOUS_USER_NOT_FOUND"


# ==================== HTTP-layer edges ====================


async def test_get_post_method_not_allowed(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(_url(chat_id), cookies=auth_cookie(user_id))

    assert response.status_code == 405
