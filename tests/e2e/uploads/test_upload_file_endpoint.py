"""
End-to-end tests for POST /v1/uploads/{chat_session_id}.
"""

import hashlib
import uuid

import pytest

from src.config.configs import settings
from src.uploads.domain.document import DocumentStatus
from tests.e2e.uploads.conftest import CONTENT

pytestmark = pytest.mark.asyncio


def _url(chat_session_id):
    return f"/v1/uploads/{chat_session_id}"


def _file(data=CONTENT, filename="notes.txt", content_type="text/plain"):
    return {"file": (filename, data, content_type)}


class TestUpload:
    async def test_stores_file_and_starts_ingestion(
        self, client, owner, object_storage, read_documents, runner
    ):
        response = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, files=_file()
        )

        assert response.status_code == 202
        [document] = await read_documents(owner.chat_session_id)
        assert document.status == DocumentStatus.UPLOADED
        assert document.size_bytes == len(CONTENT)
        assert document.checksum == hashlib.sha256(CONTENT).hexdigest()
        assert object_storage.load(document.object_key) == CONTENT
        runner.start.assert_called_once()
        assert runner.start.call_args.args[0].document_id == document.id

    async def test_returns_the_uploaded_document(self, client, owner):
        response = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, files=_file()
        )

        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["chatSessionId"] == str(owner.chat_session_id)
        assert data["filename"] == "notes.txt"
        assert data["contentType"] == "text/plain"
        assert data["status"] == DocumentStatus.UPLOADED.value
        assert data["sizeBytes"] == len(CONTENT)
        assert data["checksum"] == hashlib.sha256(CONTENT).hexdigest()


class TestDuplicateFilename:
    async def test_same_filename_in_same_session_is_a_conflict(
        self, client, owner, object_storage, read_documents, runner
    ):
        first = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, files=_file()
        )
        assert first.status_code == 202

        second = await client.post(
            _url(owner.chat_session_id),
            headers=owner.headers,
            files=_file(data=b"different content"),
        )

        assert second.status_code == 409
        assert second.json()["error"]["code"] == "DUPLICATE_FILENAME"
        [document] = await read_documents(owner.chat_session_id)
        assert object_storage.load(document.object_key) == CONTENT
        runner.start.assert_called_once()

    async def test_same_filename_in_another_session_is_allowed(
        self, client, owner, make_owner
    ):
        other_session = await make_owner(user_id=owner.user_id)

        first = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, files=_file()
        )
        second = await client.post(
            _url(other_session.chat_session_id), headers=owner.headers, files=_file()
        )

        assert (first.status_code, second.status_code) == (202, 202)

    async def test_filename_is_free_again_after_delete(self, client, owner):
        first = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, files=_file()
        )
        await client.delete(
            f"{_url(owner.chat_session_id)}/{first.json()['data']['id']}",
            headers=owner.headers,
        )

        again = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, files=_file()
        )

        assert again.status_code == 202


class TestRejectedFiles:
    @pytest.mark.parametrize(
        "upload, expected_status",
        [
            (_file(filename="program.exe"), 415),
            (_file(content_type="image/png"), 415),
            (_file(data=b""), 422),
            (
                _file(
                    data=b"x" * (settings.uploads.MAX_FILE_SIZE_MB * 1024 * 1024 + 1)
                ),
                413,
            ),
        ],
        ids=["bad-extension", "bad-content-type", "empty", "too-large"],
    )
    async def test_invalid_file_is_rejected_without_storing(
        self, client, owner, read_documents, runner, upload, expected_status
    ):
        response = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, files=upload
        )

        assert response.status_code == expected_status
        assert await read_documents(owner.chat_session_id) == []
        runner.start.assert_not_called()

    async def test_missing_file_field_is_rejected(self, client, owner):
        response = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, data={"x": "1"}
        )

        assert response.status_code == 422

    async def test_full_chat_session_is_rejected(
        self, client, owner, seed_document, read_documents
    ):
        limit = settings.uploads.MAX_DOCS_PER_SESSION
        for _ in range(limit):
            await seed_document(owner.chat_session_id)

        response = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, files=_file()
        )

        assert response.status_code == 422
        assert len(await read_documents(owner.chat_session_id)) == limit


class TestAccess:
    async def test_missing_cookie_is_unauthorized(self, client, owner):
        response = await client.post(_url(owner.chat_session_id), files=_file())

        assert response.status_code == 401

    async def test_another_users_chat_session_is_forbidden(
        self, client, owner, make_owner, read_documents, runner
    ):
        intruder = await make_owner()

        response = await client.post(
            _url(owner.chat_session_id), headers=intruder.headers, files=_file()
        )

        assert response.status_code == 403
        assert await read_documents(owner.chat_session_id) == []
        runner.start.assert_not_called()

    async def test_unknown_chat_session_is_not_found(self, client, owner):
        response = await client.post(
            _url(uuid.uuid4()), headers=owner.headers, files=_file()
        )

        assert response.status_code == 404

    async def test_malformed_chat_session_id_is_rejected(self, client, owner):
        response = await client.post(
            _url("not-a-uuid"), headers=owner.headers, files=_file()
        )

        assert response.status_code == 422


class TestRateLimit:
    async def test_uploads_beyond_the_shared_limit_are_throttled(self, client, owner):
        limit = int(settings.server.RATE_LIMIT_UPLOADS.split("/")[0])
        for _ in range(limit):
            await client.get(_url(owner.chat_session_id), headers=owner.headers)

        response = await client.post(
            _url(owner.chat_session_id), headers=owner.headers, files=_file()
        )

        assert response.status_code == 429
