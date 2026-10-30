"""
End-to-end tests for DELETE /v1/uploads/{chat_session_id}.
"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio


def _url(chat_session_id):
    return f"/v1/uploads/{chat_session_id}"


class TestDeleteAll:
    async def test_removes_every_file_and_reports_count(
        self, client, owner, seed_document, read_documents, object_storage
    ):
        documents = [await seed_document(owner.chat_session_id) for _ in range(3)]

        response = await client.delete(
            _url(owner.chat_session_id), headers=owner.headers
        )

        assert response.status_code == 200
        assert response.json()["data"] == {"deletedCount": 3}
        assert await read_documents(owner.chat_session_id) == []
        assert not any(object_storage.exists(d.object_key) for d in documents)

    async def test_leaves_other_chat_sessions_alone(
        self, client, owner, make_owner, seed_document, read_documents, object_storage
    ):
        await seed_document(owner.chat_session_id)
        other_session = await make_owner(user_id=owner.user_id)
        kept = await seed_document(other_session.chat_session_id)

        response = await client.delete(
            _url(owner.chat_session_id), headers=owner.headers
        )

        assert response.json()["data"] == {"deletedCount": 1}
        assert len(await read_documents(other_session.chat_session_id)) == 1
        assert object_storage.exists(kept.object_key) is True

    async def test_empty_chat_session_deletes_nothing(self, client, owner):
        response = await client.delete(
            _url(owner.chat_session_id), headers=owner.headers
        )

        assert response.status_code == 200
        assert response.json()["data"] == {"deletedCount": 0}

    async def test_missing_stored_file_still_deletes_row(
        self, client, owner, seed_document, read_documents
    ):
        await seed_document(owner.chat_session_id, store_file=False)

        response = await client.delete(
            _url(owner.chat_session_id), headers=owner.headers
        )

        assert response.status_code == 200
        assert await read_documents(owner.chat_session_id) == []

    async def test_old_batch_delete_route_is_gone(self, client, owner):
        response = await client.post(
            f"{_url(owner.chat_session_id)}/batch-delete",
            headers=owner.headers,
            json={"fileIds": [str(uuid.uuid4())]},
        )

        assert response.status_code in (404, 405)


class TestAccess:
    async def test_missing_cookie_is_unauthorized(
        self, client, owner, seed_document, read_documents
    ):
        await seed_document(owner.chat_session_id)

        response = await client.delete(_url(owner.chat_session_id))

        assert response.status_code == 401
        assert len(await read_documents(owner.chat_session_id)) == 1

    async def test_another_users_chat_session_is_forbidden(
        self, client, owner, make_owner, seed_document, read_documents
    ):
        await seed_document(owner.chat_session_id)
        intruder = await make_owner()

        response = await client.delete(
            _url(owner.chat_session_id), headers=intruder.headers
        )

        assert response.status_code == 403
        assert len(await read_documents(owner.chat_session_id)) == 1

    async def test_unknown_chat_session_is_not_found(self, client, owner):
        response = await client.delete(_url(uuid.uuid4()), headers=owner.headers)

        assert response.status_code == 404
