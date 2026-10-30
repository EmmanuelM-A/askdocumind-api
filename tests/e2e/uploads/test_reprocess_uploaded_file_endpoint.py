"""
End-to-end tests for POST /v1/uploads/{chat_session_id}/{file_id}/reprocess.
"""

import uuid

import pytest

from src.uploads.domain.document import DocumentStatus

pytestmark = pytest.mark.asyncio


def _url(chat_session_id, file_id):
    return f"/v1/uploads/{chat_session_id}/{file_id}/reprocess"


async def _status(read_documents, chat_session_id):
    [document] = await read_documents(chat_session_id)
    return document.status


class TestReprocess:
    async def test_failed_document_is_queued_again(
        self, client, owner, seed_document, read_documents, runner
    ):
        document = await seed_document(
            owner.chat_session_id, status=DocumentStatus.FAILED
        )

        response = await client.post(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        assert response.status_code == 202
        [stored] = await read_documents(owner.chat_session_id)
        assert stored.status == DocumentStatus.UPLOADED
        assert stored.error_message is None
        runner.start.assert_called_once()
        assert runner.start.call_args.args[0].document_id == document.id

    async def test_returns_the_standard_envelope_with_the_new_status(
        self, client, owner, seed_document
    ):
        document = await seed_document(
            owner.chat_session_id, status=DocumentStatus.FAILED
        )

        response = await client.post(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        body = response.json()
        assert body["success"] is True
        assert body["data"]["id"] == str(document.id)
        assert body["data"]["status"] == DocumentStatus.UPLOADED.value
        assert body["data"]["errorMessage"] is None

    @pytest.mark.parametrize(
        "status", [s for s in DocumentStatus if s is not DocumentStatus.FAILED]
    )
    async def test_document_not_failed_is_a_conflict(
        self, client, owner, seed_document, read_documents, runner, status
    ):
        document = await seed_document(owner.chat_session_id, status=status)

        response = await client.post(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        assert response.status_code == 409
        assert await _status(read_documents, owner.chat_session_id) == status
        runner.start.assert_not_called()

    async def test_missing_stored_file_is_a_conflict(
        self, client, owner, seed_document, read_documents, runner
    ):
        document = await seed_document(
            owner.chat_session_id, status=DocumentStatus.FAILED, store_file=False
        )

        response = await client.post(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        assert response.status_code == 409
        assert (
            await _status(read_documents, owner.chat_session_id)
            == DocumentStatus.FAILED
        )
        runner.start.assert_not_called()

    async def test_document_from_another_chat_session_is_forbidden(
        self, client, owner, make_owner, seed_document, read_documents
    ):
        other_session = await make_owner(user_id=owner.user_id)
        document = await seed_document(
            other_session.chat_session_id, status=DocumentStatus.FAILED
        )

        response = await client.post(
            _url(owner.chat_session_id, document.id), headers=owner.headers
        )

        assert response.status_code == 403
        assert (
            await _status(read_documents, other_session.chat_session_id)
            == DocumentStatus.FAILED
        )

    async def test_unknown_document_is_not_found(self, client, owner):
        response = await client.post(
            _url(owner.chat_session_id, uuid.uuid4()), headers=owner.headers
        )

        assert response.status_code == 404


class TestAccess:
    async def test_missing_cookie_is_unauthorized(self, client, owner, seed_document):
        document = await seed_document(
            owner.chat_session_id, status=DocumentStatus.FAILED
        )

        response = await client.post(_url(owner.chat_session_id, document.id))

        assert response.status_code == 401

    async def test_another_users_chat_session_is_forbidden(
        self, client, owner, make_owner, seed_document, read_documents, runner
    ):
        document = await seed_document(
            owner.chat_session_id, status=DocumentStatus.FAILED
        )
        intruder = await make_owner()

        response = await client.post(
            _url(owner.chat_session_id, document.id), headers=intruder.headers
        )

        assert response.status_code == 403
        assert (
            await _status(read_documents, owner.chat_session_id)
            == DocumentStatus.FAILED
        )
        runner.start.assert_not_called()

    async def test_malformed_file_id_is_rejected(self, client, owner):
        response = await client.post(
            _url(owner.chat_session_id, "not-a-uuid"), headers=owner.headers
        )

        assert response.status_code == 422

    async def test_get_is_not_allowed(self, client, owner):
        response = await client.get(
            _url(owner.chat_session_id, uuid.uuid4()), headers=owner.headers
        )

        assert response.status_code == 405
