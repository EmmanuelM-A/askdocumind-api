"""
End-to-end tests for GET /v1/uploads/{chat_session_id}.
"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio


def _url(chat_session_id):
    return f"/v1/uploads/{chat_session_id}"


class TestListing:
    async def test_returns_documents_newest_first(self, client, owner, seed_document):
        seeded = [await seed_document(owner.chat_session_id) for _ in range(3)]

        response = await client.get(_url(owner.chat_session_id), headers=owner.headers)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert [item["id"] for item in body["data"]["items"]] == [
            str(d.id) for d in reversed(seeded)
        ]
        assert body["data"]["total"] == 3

    async def test_items_are_viewable_documents(self, client, owner, seed_document):
        document = await seed_document(owner.chat_session_id, filename="notes.txt")

        response = await client.get(_url(owner.chat_session_id), headers=owner.headers)

        [item] = response.json()["data"]["items"]
        assert item["id"] == str(document.id)
        assert item["chatSessionId"] == str(owner.chat_session_id)
        assert item["filename"] == "notes.txt"
        assert item["status"] == document.status.value
        assert "objectKey" not in item

    async def test_returns_the_requested_page(self, client, owner, seed_document):
        seeded = [await seed_document(owner.chat_session_id) for _ in range(3)]

        response = await client.get(
            _url(owner.chat_session_id),
            headers=owner.headers,
            params={"page": 2, "limit": 2},
        )

        data = response.json()["data"]
        assert [item["id"] for item in data["items"]] == [str(seeded[0].id)]
        assert data["total"] == 3
        assert data["page"] == 2
        assert data["size"] == 2

    async def test_empty_chat_session_returns_no_items(self, client, owner):
        response = await client.get(_url(owner.chat_session_id), headers=owner.headers)

        assert response.status_code == 200
        assert response.json()["data"]["items"] == []
        assert response.json()["data"]["total"] == 0

    async def test_excludes_documents_from_other_chat_sessions(
        self, client, owner, make_owner, seed_document
    ):
        mine = await seed_document(owner.chat_session_id)
        other_session = await make_owner(user_id=owner.user_id)
        await seed_document(other_session.chat_session_id)

        response = await client.get(_url(owner.chat_session_id), headers=owner.headers)

        assert [item["id"] for item in response.json()["data"]["items"]] == [
            str(mine.id)
        ]

    @pytest.mark.parametrize(
        "params",
        [{"page": 0}, {"limit": 0}, {"limit": 101}, {"page": "abc"}],
        ids=["page-zero", "limit-zero", "limit-too-large", "page-not-a-number"],
    )
    async def test_invalid_pagination_is_rejected(self, client, owner, params):
        response = await client.get(
            _url(owner.chat_session_id), headers=owner.headers, params=params
        )

        assert response.status_code == 422


class TestAccess:
    async def test_missing_cookie_is_unauthorized(self, client, owner):
        response = await client.get(_url(owner.chat_session_id))

        assert response.status_code == 401

    async def test_another_users_chat_session_is_forbidden(
        self, client, owner, make_owner, seed_document
    ):
        await seed_document(owner.chat_session_id)
        intruder = await make_owner()

        response = await client.get(
            _url(owner.chat_session_id), headers=intruder.headers
        )

        assert response.status_code == 403

    async def test_unknown_chat_session_is_not_found(self, client, owner):
        response = await client.get(_url(uuid.uuid4()), headers=owner.headers)

        assert response.status_code == 404

    async def test_malformed_chat_session_id_is_rejected(self, client, owner):
        response = await client.get(_url("not-a-uuid"), headers=owner.headers)

        assert response.status_code == 422
