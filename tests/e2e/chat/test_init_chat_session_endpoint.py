"""
End-to-end tests for POST /api/sessions/init (initialize or retrieve chat
session). No dependency is mocked anywhere in this file.
"""

from uuid import UUID, uuid4

from src.config.configs import settings

ENDPOINT = "/api/sessions/init"
COOKIE_NAME = settings.auth.COOKIE_NAME


# ============================ Happy path ============================


async def test_init_creates_new_session_returns_200(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT, json={"title": "My Chat"}, cookies=auth_cookie(user_id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Chat session initialized successfully."
    UUID(body["data"]["chat_id"])  # does not raise


async def test_init_persists_row_with_correct_title_and_owner(
    app_client, seed_user, auth_cookie, chat_session_repo
):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT, json={"title": "Persisted Init Chat"}, cookies=auth_cookie(user_id)
    )
    chat_id = UUID(response.json()["data"]["chat_id"])

    stored = await chat_session_repo.get_by_id(chat_id)

    assert stored is not None
    assert stored.title == "Persisted Init Chat"
    assert stored.user_id == user_id


async def test_init_repeated_calls_return_same_session_id(
    app_client, seed_user, auth_cookie, chat_session_repo
):
    user_id = await seed_user()
    cookies = auth_cookie(user_id)

    first = app_client.post(ENDPOINT, json={"title": "First"}, cookies=cookies)
    second = app_client.post(ENDPOINT, json={"title": "Second"}, cookies=cookies)

    first_id = first.json()["data"]["chat_id"]
    second_id = second.json()["data"]["chat_id"]

    assert first_id == second_id

    all_sessions = await chat_session_repo.list_by()
    matching = [s for s in all_sessions if str(s.user_id) == str(user_id)]
    assert len(matching) == 1


async def test_init_does_not_enforce_max_chats_per_user(app_client, seed_user, auth_cookie):
    """Unlike POST /sessions, /init has no MAX_CHATS_PER_USER check - it just
    returns the existing session, so repeated calls never 422."""
    user_id = await seed_user()
    cookies = auth_cookie(user_id)

    for _ in range(3):
        response = app_client.post(ENDPOINT, json={"title": "Chat"}, cookies=cookies)
        assert response.status_code == 200


async def test_init_two_different_users_get_distinct_sessions(
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

    assert response_a.json()["data"]["chat_id"] != response_b.json()["data"]["chat_id"]


# ==================== Auth failure matrix ====================


async def test_init_no_cookie_returns_422(app_client):
    response = app_client.post(ENDPOINT, json={"title": "Chat"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_COOKIE_VALUE"


async def test_init_garbage_cookie_returns_422(app_client):
    response = app_client.post(
        ENDPOINT, json={"title": "Chat"}, cookies={COOKIE_NAME: "not-a-real-token"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_init_valid_signature_nonexistent_user_returns_404(app_client, token_manager):
    random_user_id = uuid4()
    cookie_token = token_manager.create_token(random_user_id)

    response = app_client.post(
        ENDPOINT, json={"title": "Chat"}, cookies={COOKIE_NAME: cookie_token}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANONYMOUS_USER_NOT_FOUND"


# ==================== Validation ====================


async def test_init_missing_title_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(ENDPOINT, json={}, cookies=auth_cookie(user_id))

    assert response.status_code == 422


async def test_init_non_string_title_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT, json={"title": ["not", "a", "string"]}, cookies=auth_cookie(user_id)
    )

    assert response.status_code == 422


# ==================== HTTP-layer edges ====================


async def test_init_get_falls_through_to_session_id_route_as_422(
    app_client, seed_user, auth_cookie
):
    """There's no exact GET /sessions/init route, so this matches the
    parameterized GET /sessions/{session_id} route with session_id="init",
    which fails UUID parsing -> 422 (not 405, since no exact-path route
    exists to register a method conflict against)."""
    user_id = await seed_user()

    response = app_client.get(ENDPOINT, cookies=auth_cookie(user_id))

    assert response.status_code == 422


async def test_init_trailing_slash_returns_404(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        f"{ENDPOINT}/", json={"title": "Chat"}, cookies=auth_cookie(user_id), follow_redirects=False
    )

    assert response.status_code == 404
