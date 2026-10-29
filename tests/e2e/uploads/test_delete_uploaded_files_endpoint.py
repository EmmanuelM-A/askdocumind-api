"""
End-to-end tests for POST /v1/uploads/{chat_session_id}/batch-delete.
"""

import uuid

import pytest

from src.config.configs import settings

pytestmark = pytest.mark.asyncio


def _url(chat_session_id):
    return f"/v1/uploads/{chat_session_id}/batch-delete"


def _body(*ids):
    return {"fileIds": [str(i) for i in ids]}


class TestBatchDelete:
    async def test_removes_listed_files_and_reports_count(
        self, client, owner, seed_document, read_documents, object_storage
    ):
        doomed = [await seed_document(owner.chat_session_id) for _ in range(2)]
        survivor = await seed_document(owner.chat_session_id)

        response = await client.post(
            _url(owner.chat_session_id),
            headers=owner.headers,
            json=_body(*(d.id for d in doomed)),
        )

        assert response.status_code == 200
        assert response.json()["data"] == {"deletedCount": 2}
        assert [d.id for d in await read_documents(owner.chat_session_id)] == [
            survivor.id
        ]
        assert not any(object_storage.exists(d.object_key) for d in doomed)
        assert object_storage.exists(survivor.object_key) is True

    async def test_skips_unknown_and_other_session_ids(
        self, client, owner, make_owner, seed_document, read_documents, object_storage
    ):
        mine = await seed_document(owner.chat_session_id)
        other_session = await make_owner(user_id=owner.user_id)
        foreign = await seed_document(other_session.chat_session_id)

        response = await client.post(
            _url(owner.chat_session_id),
            headers=owner.headers,
            json=_body(mine.id, foreign.id, uuid.uuid4()),
        )

        assert response.status_code == 200
        assert response.json()["data"] == {"deletedCount": 1}
        assert len(await read_documents(other_session.chat_session_id)) == 1
        assert object_storage.exists(foreign.object_key) is True

    async def test_duplicate_ids_count_once(
        self, client, owner, seed_document, read_documents
    ):
        document = await seed_document(owner.chat_session_id)

        response = await client.post(
            _url(owner.chat_session_id),
            headers=owner.headers,
            json=_body(document.id, document.id),
        )

        assert response.json()["data"] == {"deletedCount": 1}
        assert await read_documents(owner.chat_session_id) == []

    async def test_missing_stored_file_still_deletes_row(
        self, client, owner, seed_document, read_documents
    ):
        document = await seed_document(owner.chat_session_id, store_file=False)

        response = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, json=_body(document.id)
        )

        assert response.status_code == 200
        assert await read_documents(owner.chat_session_id) == []

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"fileIds": []},
            {"fileIds": ["not-a-uuid"]},
            _body(
                *(
                    uuid.uuid4()
                    for _ in range(settings.uploads.MAX_DOCS_PER_SESSION + 1)
                )
            ),
        ],
        ids=["missing", "empty", "malformed-id", "too-many"],
    )
    async def test_invalid_body_is_rejected(self, client, owner, body):
        response = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, json=body
        )

        assert response.status_code == 422


class TestAccess:
    async def test_missing_cookie_is_unauthorized(
        self, client, owner, seed_document, read_documents
    ):
        document = await seed_document(owner.chat_session_id)

        response = await client.post(
            _url(owner.chat_session_id), json=_body(document.id)
        )

        assert response.status_code == 401
        assert len(await read_documents(owner.chat_session_id)) == 1

    async def test_another_users_chat_session_is_forbidden(
        self, client, owner, make_owner, seed_document, read_documents
    ):
        document = await seed_document(owner.chat_session_id)
        intruder = await make_owner()

        response = await client.post(
            _url(owner.chat_session_id),
            headers=intruder.headers,
            json=_body(document.id),
        )

        assert response.status_code == 403
        assert len(await read_documents(owner.chat_session_id)) == 1

    async def test_unknown_chat_session_is_not_found(self, client, owner):
        response = await client.post(
            _url(uuid.uuid4()), headers=owner.headers, json=_body(uuid.uuid4())
        )

        assert response.status_code == 404
