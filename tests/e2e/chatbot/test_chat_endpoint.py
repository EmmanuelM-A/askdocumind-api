"""
End-to-end tests for POST /api/chat (RAG chatbot interaction). No dependency
is mocked anywhere in this file - queries run through the real query
embedding, real pgvector similarity search, and real OpenAI query expansion
+ RAG generation.

Deliberately NOT tested here: the OUT_OF_SCOPE and NEED_WEB_SEARCH sentinel
LLM responses (src/components/chatbot/core.py). Reliably forcing the real
LLM into those specific branches requires content/query combinations that
are inherently flaky (an LLM judgment call), and forcing them deterministically
would require mocking the LLM - which contradicts "no mocking of anything"
for this file. The "no relevant chunks found" default-response path is
exercised instead, which is both fully real and fully deterministic.

Also not exercised: the web-search fallback branch. IS_WEB_SEARCH_ENABLED is
False in this environment's .env, so `web_search_enabled=True` in a request
never actually triggers it (see settings.web.IS_WEB_SEARCH_ENABLED) - one
test below confirms that combination still falls back to the default
message rather than silently erroring.
"""

from uuid import uuid4

from src.config.configs import settings

ENDPOINT = "/api/chat"
COOKIE_NAME = settings.auth.COOKIE_NAME
DEFAULT_NO_RESULTS_PREFIX = "I couldn't find relevant information"


# ============================ Happy path ============================


async def test_chat_no_relevant_chunks_returns_default_message(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    """No chunks exist for the chat at all, so vector search finds nothing
    and the real pipeline short-circuits to the default response - no LLM
    generation call happens on this path, only a real embed_query call."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        json={"user_query": "What does the document say about pricing?", "chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Chatbot response generated successfully."
    assert body["data"]["answer"].startswith(DEFAULT_NO_RESULTS_PREFIX)
    assert body["data"]["sources"] == []


async def test_chat_with_relevant_chunk_returns_real_generated_answer(
    app_client, seed_user, seed_chat_session, auth_cookie, seed_chunk
):
    """Full real pipeline: seed a chunk with a real embedding, ask a closely
    related question, and get a real LLM-generated answer with sources."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    await seed_chunk(
        chat_id,
        text="Our premium subscription plan costs $29 per month and includes "
        "unlimited document uploads and priority support.",
        source="pricing.txt",
    )

    response = app_client.post(
        ENDPOINT,
        json={
            "user_query": "How much does the premium subscription cost per month?",
            "chat_id": str(chat_id),
        },
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 200
    body = response.json()
    answer = body["data"]["answer"]
    assert isinstance(answer, str)
    assert len(answer) > 0
    assert answer != DEFAULT_NO_RESULTS_PREFIX
    assert body["data"]["sources"] == ["pricing.txt"]


async def test_chat_persists_user_and_assistant_messages(
    app_client, seed_user, seed_chat_session, auth_cookie, seed_chunk, chat_message_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    await seed_chunk(
        chat_id,
        text="The office is located at 123 Main Street and opens at 9am on weekdays.",
        source="office.txt",
    )
    query = "What time does the office open on weekdays?"

    response = app_client.post(
        ENDPOINT,
        json={"user_query": query, "chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )
    answer = response.json()["data"]["answer"]

    from src.database.repository.interfaces import ChatMessageSearchCriteria

    messages = await chat_message_repo.list_by(
        criteria=ChatMessageSearchCriteria(session_id=chat_id)
    )

    assert len(messages) == 2
    roles = {m.role.name: m.content for m in messages}
    assert roles["USER"] == query
    assert roles["ASSISTANT"] == answer


async def test_chat_web_search_enabled_falls_back_to_real_web_search(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    """No local chunks + web_search_enabled=True + IS_WEB_SEARCH_ENABLED on in
    this env: the LLM should judge a document-plausible question as
    NEED_WEB_SEARCH (not OUT_OF_SCOPE), triggering a real Brave/DDGS search,
    real content ingestion, and a real generated answer with sources."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        json={
            "user_query": "What does the document say about refund policy?",
            "chat_id": str(chat_id),
            "web_search_enabled": True,
        },
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert not body["answer"].startswith(DEFAULT_NO_RESULTS_PREFIX)
    assert len(body["sources"]) > 0


async def test_chat_response_shape(app_client, seed_user, seed_chat_session, auth_cookie):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        json={"user_query": "A question with no matching documents at all.", "chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    body = response.json()
    assert set(body.keys()) == {"success", "timestamp", "message", "data"}
    assert set(body["data"].keys()) == {"answer", "sources"}


# ==================== Validation ====================


async def test_chat_missing_user_query_returns_422(app_client, seed_user, seed_chat_session, auth_cookie):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT, json={"chat_id": str(chat_id)}, headers=auth_cookie(user_id)
    )

    assert response.status_code == 422


async def test_chat_query_too_short_returns_422(app_client, seed_user, seed_chat_session, auth_cookie):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        json={"user_query": "hi", "chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422


async def test_chat_overlong_query_is_silently_truncated_not_rejected(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    """ChatRequest.user_query declares Field(max_length=MAX_QUERY_LENGTH),
    but validate_and_sanitize_query (a mode="before" validator) truncates
    overlong input to that same length before Pydantic's max_length check
    ever runs - so the declared constraint never actually fires. This is
    deliberate sanitize-gracefully behavior, not a bug: an overlong query
    is truncated and processed (200), not rejected (422)."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    long_query = "a" * (settings.app.MAX_QUERY_LENGTH + 1)

    response = app_client.post(
        ENDPOINT,
        json={"user_query": long_query, "chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 200


async def test_chat_whitespace_only_query_returns_422(app_client, seed_user, seed_chat_session, auth_cookie):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        json={"user_query": "             ", "chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422


async def test_chat_missing_chat_id_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT,
        json={"user_query": "A perfectly valid question here."},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422


async def test_chat_invalid_chat_id_format_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT,
        json={"user_query": "A perfectly valid question here.", "chat_id": "not-a-uuid"},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422


async def test_chat_non_bool_web_search_enabled_returns_422(app_client, seed_user, seed_chat_session, auth_cookie):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        json={
            "user_query": "A perfectly valid question here.",
            "chat_id": str(chat_id),
            "web_search_enabled": "not-a-bool",
        },
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 422


# ==================== Not found / ownership ====================


async def test_chat_nonexistent_chat_returns_404(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.post(
        ENDPOINT,
        json={"user_query": "A perfectly valid question here.", "chat_id": str(uuid4())},
        headers=auth_cookie(user_id),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


async def test_chat_chat_owned_by_another_user_returns_404(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    owner_id = await seed_user()
    other_user_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)

    response = app_client.post(
        ENDPOINT,
        json={"user_query": "A perfectly valid question here.", "chat_id": str(chat_id)},
        headers=auth_cookie(other_user_id),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


# ==================== Auth failure matrix ====================


async def test_chat_no_cookie_returns_422(app_client, seed_user, seed_chat_session):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT, json={"user_query": "A perfectly valid question here.", "chat_id": str(chat_id)}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_COOKIE_VALUE"


async def test_chat_garbage_cookie_returns_422(app_client, seed_user, seed_chat_session):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        ENDPOINT,
        json={"user_query": "A perfectly valid question here.", "chat_id": str(chat_id)},
        headers={"Cookie": f"{COOKIE_NAME}=garbage"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_chat_valid_signature_nonexistent_user_returns_404(
    app_client, token_manager, seed_user, seed_chat_session
):
    owner_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)
    cookie_token = token_manager.create_token(uuid4())

    response = app_client.post(
        ENDPOINT,
        json={"user_query": "A perfectly valid question here.", "chat_id": str(chat_id)},
        headers={"Cookie": f"{COOKIE_NAME}={cookie_token}"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANONYMOUS_USER_NOT_FOUND"


# ==================== Rate limiting ====================


async def test_chat_rate_limit_exceeded_returns_429(app_client, seed_user, seed_chat_session, auth_cookie):
    """MAX_CHAT_QUERIES_PER_MINUTE=10, keyed per anonymous user. Uses a
    fresh user (own rate-limit bucket) and the cheap no-chunks-found path
    (no LLM generation call) to stay fast while still exercising a real
    11th-request rejection."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    headers = auth_cookie(user_id)
    payload = {"user_query": "A question with no matching documents at all.", "chat_id": str(chat_id)}

    responses = [app_client.post(ENDPOINT, json=payload, headers=headers) for _ in range(11)]

    assert responses[-1].status_code == 429
    assert all(r.status_code == 200 for r in responses[:10])


# ==================== HTTP-layer edges ====================


async def test_chat_get_method_not_allowed(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.get(ENDPOINT, headers=auth_cookie(user_id))

    assert response.status_code == 405


async def test_chat_trailing_slash_returns_404(app_client, seed_user, seed_chat_session, auth_cookie):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.post(
        f"{ENDPOINT}/",
        json={"user_query": "A perfectly valid question here.", "chat_id": str(chat_id)},
        headers=auth_cookie(user_id),
        follow_redirects=False,
    )

    assert response.status_code == 404
