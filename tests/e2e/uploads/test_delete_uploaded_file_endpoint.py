"""
End-to-end tests for DELETE /v1/uploads/{chat_session_id}/{file_id}.
"""

import uuid

import pytest

from src.uploads.domain.document import DocumentStatus

pytestmark = pytest.mark.asyncio


def _url(chat_session_id, file_id):
    return f"/v1/uploads/{chat_session_id}/{file_id}"


class TestDelete:
    async def test_removes_row_and_stored_file(
        self, client, owner, seed_document, read_documents, object_storage
    ):
        document = await seed_document(owner.chat_session_id)

        response = await client.delete(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert await read_documents(owner.chat_session_id) == []
        assert object_storage.exists(document.object_key) is False

    async def test_leaves_other_documents_alone(
        self, client, owner, seed_document, read_documents
    ):
        doomed = await seed_document(owner.chat_session_id)
        survivor = await seed_document(owner.chat_session_id)

        await client.delete(
            _url(owner.chat_session_id, doomed.id), headers=owner.headers
        )

        assert [d.id for d in await read_documents(owner.chat_session_id)] == [
            survivor.id
        ]

    @pytest.mark.parametrize("status", list(DocumentStatus))
    async def test_deletes_in_any_status(
        self, client, owner, seed_document, read_documents, status
    ):
        document = await seed_document(owner.chat_session_id, status=status)

        response = await client.delete(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        assert response.status_code == 200
        assert await read_documents(owner.chat_session_id) == []

    async def test_missing_stored_file_still_deletes_row(
        self, client, owner, seed_document, read_documents
    ):
        document = await seed_document(owner.chat_session_id, store_file=False)

        response = await client.delete(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        assert response.status_code == 200
        assert await read_documents(owner.chat_session_id) == []

    async def test_unknown_file_succeeds(self, client, owner):
        response = await client.delete(
            _url(owner.chat_session_id, uuid.uuid4()), headers=owner.headers
        )

        assert response.status_code == 200

    async def test_file_from_another_chat_session_is_not_found(
        self, client, owner, make_owner, seed_document, read_documents, object_storage
    ):
        other_session = await make_owner(user_id=owner.user_id)
        document = await seed_document(other_session.chat_session_id)

        response = await client.delete(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        assert response.status_code == 404
        assert len(await read_documents(other_session.chat_session_id)) == 1
        assert object_storage.exists(document.object_key) is True


class TestAccess:
    async def test_missing_cookie_is_unauthorized(
        self, client, owner, seed_document, read_documents
    ):
        document = await seed_document(owner.chat_session_id)

        response = await client.delete(_url(owner.chat_session_id, document.id))

        assert response.status_code == 401
        assert len(await read_documents(owner.chat_session_id)) == 1

    async def test_another_users_chat_session_is_forbidden(
        self, client, owner, make_owner, seed_document, read_documents
    ):
        document = await seed_document(owner.chat_session_id)
        intruder = await make_owner()

        response = await client.delete(
            _url(owner.chat_session_id, document.id), headers=intruder.headers
        )

        assert response.status_code == 403
        assert len(await read_documents(owner.chat_session_id)) == 1

    async def test_unknown_chat_session_is_not_found(self, client, owner):
        response = await client.delete(
            _url(uuid.uuid4(), uuid.uuid4()), headers=owner.headers
        )

        assert response.status_code == 404

    async def test_malformed_file_id_is_rejected(self, client, owner):
        response = await client.delete(
            _url(owner.chat_session_id, "not-a-uuid"), headers=owner.headers
        )

        assert response.status_code == 422
