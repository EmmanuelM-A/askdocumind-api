"""
End-to-end tests for GET /api/documents?chat_id=... (list uploaded
documents). No dependency is mocked anywhere in this file.
"""

from uuid import uuid4

from src.config.configs import settings
from src.database.models import Document

ENDPOINT = "/api/documents"
COOKIE_NAME = settings.auth.COOKIE_NAME


def _url(chat_id) -> str:
    return f"{ENDPOINT}?chat_id={chat_id}"


# ============================ Happy path ============================


async def test_list_empty_chat_returns_empty_list(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.get(_url(chat_id), headers=auth_cookie(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Successfully fetched 0 document(s)."
    assert body["data"]["documents"] == []


async def test_list_returns_uploaded_document_with_correct_shape(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    await document_repo.create(
        Document(session_id=chat_id, source="report.txt", source_size=42)
    )

    response = app_client.get(_url(chat_id), headers=auth_cookie(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Successfully fetched 1 document(s)."
    [doc] = body["data"]["documents"]
    assert doc["source"] == "report.txt"
    assert doc["source_size"] == 42
    assert doc["session_id"] == str(chat_id)
    assert set(doc.keys()) == {
        "id",
        "session_id",
        "source",
        "source_size",
        "source_type",
        "processing_status",
        "created_at",
        "updated_at",
    }


async def test_list_via_real_upload_pipeline(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    """Upload a real document through the actual pipeline, then confirm it
    shows up via the list endpoint with COMPLETED status."""
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    headers = auth_cookie(user_id)

    app_client.post(
        ENDPOINT,
        files=[("documents", ("uploaded.txt", b"Some real content.", "text/plain"))],
        data={"chat_id": str(chat_id)},
        headers=headers,
    )

    response = app_client.get(_url(chat_id), headers=headers)

    [doc] = response.json()["data"]["documents"]
    assert doc["source"] == "uploaded.txt"
    assert doc["processing_status"] == "COMPLETED"


async def test_list_only_returns_documents_for_requested_chat(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    user_id = await seed_user()
    chat_a = await seed_chat_session(user_id, title="Chat A")
    await document_repo.create(
        Document(session_id=chat_a, source="in-a.txt", source_size=10)
    )

    response = app_client.get(_url(chat_a), headers=auth_cookie(user_id))

    docs = response.json()["data"]["documents"]
    assert len(docs) == 1
    assert docs[0]["source"] == "in-a.txt"


# ==================== Not found / ownership ====================


async def test_list_nonexistent_chat_returns_404(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.get(_url(uuid4()), headers=auth_cookie(user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


async def test_list_chat_owned_by_another_user_returns_404(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    owner_id = await seed_user()
    other_user_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)

    response = app_client.get(_url(chat_id), headers=auth_cookie(other_user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


# ==================== Validation ====================


async def test_list_missing_chat_id_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.get(ENDPOINT, headers=auth_cookie(user_id))

    assert response.status_code == 422


async def test_list_invalid_chat_id_format_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.get(
        f"{ENDPOINT}?chat_id=not-a-uuid", headers=auth_cookie(user_id)
    )

    assert response.status_code == 422


# ==================== Auth failure matrix ====================


async def test_list_no_cookie_returns_422(app_client, seed_user, seed_chat_session):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.get(_url(chat_id))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_COOKIE_VALUE"


async def test_list_garbage_cookie_returns_422(app_client, seed_user, seed_chat_session):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.get(_url(chat_id), headers={"Cookie": f"{COOKIE_NAME}=garbage"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_list_valid_signature_nonexistent_user_returns_404(
    app_client, token_manager, seed_user, seed_chat_session
):
    owner_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)
    cookie_token = token_manager.create_token(uuid4())

    response = app_client.get(_url(chat_id), headers={"Cookie": f"{COOKIE_NAME}={cookie_token}"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANONYMOUS_USER_NOT_FOUND"


# ==================== HTTP-layer edges ====================


async def test_list_delete_without_document_id_not_allowed(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.delete(_url(chat_id), headers=auth_cookie(user_id))

    assert response.status_code == 405
