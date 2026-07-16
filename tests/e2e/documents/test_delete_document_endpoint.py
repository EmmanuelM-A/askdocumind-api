"""
End-to-end tests for DELETE /api/documents/{document_id}?chat_id=...
No dependency is mocked anywhere in this file.
"""

from uuid import uuid4

from src.config.configs import settings
from src.database.models import Document

ENDPOINT = "/api/documents"
COOKIE_NAME = settings.auth.COOKIE_NAME


def _url(document_id, chat_id) -> str:
    return f"{ENDPOINT}/{document_id}?chat_id={chat_id}"


# ============================ Happy path ============================


async def test_delete_returns_200(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    doc_id = await document_repo.create(
        Document(session_id=chat_id, filename="delete-me.txt", file_size=10)
    )

    response = app_client.delete(_url(doc_id, chat_id), headers=auth_cookie(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == "Successfully deleted the document."


async def test_delete_actually_removes_row_from_db(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    doc_id = await document_repo.create(
        Document(session_id=chat_id, filename="gone.txt", file_size=10)
    )

    app_client.delete(_url(doc_id, chat_id), headers=auth_cookie(user_id))

    from src.database.repository.interfaces import DocumentSearchCriteria

    remaining = await document_repo.list_by(
        criteria=DocumentSearchCriteria(session_id=chat_id)
    )
    assert remaining == []


async def test_delete_does_not_affect_other_documents(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    doc_a = await document_repo.create(
        Document(session_id=chat_id, filename="a.txt", file_size=10)
    )
    doc_b = await document_repo.create(
        Document(session_id=chat_id, filename="b.txt", file_size=10)
    )

    app_client.delete(_url(doc_a, chat_id), headers=auth_cookie(user_id))

    from src.database.repository.interfaces import DocumentSearchCriteria

    remaining = await document_repo.list_by(
        criteria=DocumentSearchCriteria(session_id=chat_id)
    )
    assert [d.id for d in remaining] == [doc_b]


# ==================== Not found / ownership ====================


async def test_delete_nonexistent_document_returns_404(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.delete(_url(uuid4(), chat_id), headers=auth_cookie(user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


async def test_delete_nonexistent_chat_returns_404(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.delete(_url(uuid4(), uuid4()), headers=auth_cookie(user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


async def test_delete_chat_owned_by_another_user_returns_404(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    owner_id = await seed_user()
    other_user_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)
    doc_id = await document_repo.create(
        Document(session_id=chat_id, filename="a.txt", file_size=10)
    )

    response = app_client.delete(
        _url(doc_id, chat_id), headers=auth_cookie(other_user_id)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"


async def test_delete_document_belonging_to_different_chat_returns_404(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    """The document exists but under a different chat than the one named in
    the query string - lookup filters by id+session_id together, so this
    looks identical to not-found."""
    user_id = await seed_user()
    chat_a = await seed_chat_session(user_id, title="Chat A")
    chat_b = await seed_chat_session(user_id, title="Chat B")

    # POST /sessions enforces MAX_CHATS_PER_USER=1, but we're seeding
    # directly via the repository here, bypassing that service-layer rule -
    # both chats exist and are owned by the same user for this test's purposes.
    doc_id = await document_repo.create(
        Document(session_id=chat_a, filename="a.txt", file_size=10)
    )

    response = app_client.delete(_url(doc_id, chat_b), headers=auth_cookie(user_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


async def test_delete_twice_returns_404_on_second_call(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    doc_id = await document_repo.create(
        Document(session_id=chat_id, filename="a.txt", file_size=10)
    )
    headers = auth_cookie(user_id)

    first = app_client.delete(_url(doc_id, chat_id), headers=headers)
    second = app_client.delete(_url(doc_id, chat_id), headers=headers)

    assert first.status_code == 200
    assert second.status_code == 404
    assert second.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


# ==================== Validation ====================


async def test_delete_missing_chat_id_query_returns_422(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    doc_id = await document_repo.create(
        Document(session_id=chat_id, filename="a.txt", file_size=10)
    )

    response = app_client.delete(f"{ENDPOINT}/{doc_id}", headers=auth_cookie(user_id))

    assert response.status_code == 422


async def test_delete_invalid_document_id_path_returns_422(
    app_client, seed_user, seed_chat_session, auth_cookie
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)

    response = app_client.delete(
        f"{ENDPOINT}/not-a-uuid?chat_id={chat_id}", headers=auth_cookie(user_id)
    )

    assert response.status_code == 422


async def test_delete_invalid_chat_id_query_returns_422(app_client, seed_user, auth_cookie):
    user_id = await seed_user()

    response = app_client.delete(
        f"{ENDPOINT}/{uuid4()}?chat_id=not-a-uuid", headers=auth_cookie(user_id)
    )

    assert response.status_code == 422


# ==================== Auth failure matrix ====================


async def test_delete_no_cookie_returns_422(
    app_client, seed_user, seed_chat_session, document_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    doc_id = await document_repo.create(
        Document(session_id=chat_id, filename="a.txt", file_size=10)
    )

    response = app_client.delete(_url(doc_id, chat_id))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NO_COOKIE_VALUE"


async def test_delete_garbage_cookie_returns_422(
    app_client, seed_user, seed_chat_session, document_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    doc_id = await document_repo.create(
        Document(session_id=chat_id, filename="a.txt", file_size=10)
    )

    response = app_client.delete(_url(doc_id, chat_id), headers={"Cookie": f"{COOKIE_NAME}=garbage"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_USER_SIGNATURE"


async def test_delete_valid_signature_nonexistent_user_returns_404(
    app_client, token_manager, seed_user, seed_chat_session, document_repo
):
    owner_id = await seed_user()
    chat_id = await seed_chat_session(owner_id)
    doc_id = await document_repo.create(
        Document(session_id=chat_id, filename="a.txt", file_size=10)
    )
    cookie_token = token_manager.create_token(uuid4())

    response = app_client.delete(
        _url(doc_id, chat_id), headers={"Cookie": f"{COOKIE_NAME}={cookie_token}"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANONYMOUS_USER_NOT_FOUND"


# ==================== HTTP-layer edges ====================


async def test_delete_get_method_not_allowed_on_document_path(
    app_client, seed_user, seed_chat_session, auth_cookie, document_repo
):
    user_id = await seed_user()
    chat_id = await seed_chat_session(user_id)
    doc_id = await document_repo.create(
        Document(session_id=chat_id, filename="a.txt", file_size=10)
    )

    response = app_client.get(_url(doc_id, chat_id), headers=auth_cookie(user_id))

    assert response.status_code == 405
