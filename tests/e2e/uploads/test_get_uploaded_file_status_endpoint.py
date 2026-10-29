"""
End-to-end tests for GET /v1/uploads/{chat_session_id}/{document_id}/status.
"""

import uuid

import pytest

from src.uploads.domain.document import DocumentStatus

pytestmark = pytest.mark.asyncio


def _url(chat_session_id, document_id):
    return f"/v1/uploads/{chat_session_id}/{document_id}/status"


class TestStatus:
    @pytest.mark.parametrize("status", list(DocumentStatus))
    async def test_returns_the_document_status(
        self, client, owner, seed_document, status
    ):
        document = await seed_document(owner.chat_session_id, status=status)

        response = await client.get(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["data"] == {"status": status.value}

    async def test_document_from_another_chat_session_is_not_found(
        self, client, owner, make_owner, seed_document
    ):
        other_session = await make_owner(user_id=owner.user_id)
        document = await seed_document(other_session.chat_session_id)

        response = await client.get(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        assert response.status_code == 404

    async def test_unknown_document_is_not_found(self, client, owner):
        response = await client.get(
            _url(owner.chat_session_id, uuid.uuid4()), headers=owner.headers
        )

        assert response.status_code == 404


class TestAccess:
    async def test_missing_cookie_is_unauthorized(self, client, owner, seed_document):
        document = await seed_document(owner.chat_session_id)

        response = await client.get(_url(owner.chat_session_id, document.id))

        assert response.status_code == 401

    async def test_another_users_chat_session_is_forbidden(
        self, client, owner, make_owner, seed_document
    ):
        document = await seed_document(owner.chat_session_id)
        intruder = await make_owner()

        response = await client.get(
            _url(owner.chat_session_id, document.id), headers=intruder.headers
        )

        assert response.status_code == 403

    async def test_unknown_chat_session_is_not_found(self, client, owner):
        response = await client.get(
            _url(uuid.uuid4(), uuid.uuid4()), headers=owner.headers
        )

        assert response.status_code == 404

    @pytest.mark.parametrize("bad", ["chat_session_id", "document_id"])
    async def test_malformed_ids_are_rejected(self, client, owner, bad):
        chat_session_id = (
            "not-a-uuid" if bad == "chat_session_id" else owner.chat_session_id
        )
        document_id = "not-a-uuid" if bad == "document_id" else uuid.uuid4()

        response = await client.get(
            _url(chat_session_id, document_id), headers=owner.headers
        )

        assert response.status_code == 422
