"""
Integration tests for UploadService against a real database and S3 bucket.

Database work runs inside the rolled-back test session. Files go to a
throwaway bucket that is removed at the end of the run.
"""

import hashlib
import io
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import UploadFile, status
from sqlalchemy import select
from starlette.datastructures import Headers

from src.auth.models.user import User
from src.auth.repository.user_repository_impl import UserRepositoryImpl
from src.chat_session.models.chat_session import ChatSession
from src.chat_session.repository.chat_session_repository_impl import (
    ChatSessionRepositoryImpl,
)
from src.config.configs import settings
from src.database.utils import Pagination
from src.exceptions import object_storage_error
from src.exceptions.base import ApiException
from src.uploads.domain.document import DocumentStatus
from src.uploads.models.document import Document
from src.uploads.repository.document_repository_impl import DocumentRepositoryImpl
from src.uploads.services.upload_service import UploadService

pytestmark = pytest.mark.asyncio

CONTENT = b"The quick brown fox jumps over the lazy dog."


def _file(data=CONTENT, filename="notes.txt", content_type="text/plain"):
    return UploadFile(
        file=io.BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


async def _new_owner(session):
    user = User()
    session.add(user)
    await session.flush()
    chat_session = ChatSession(user_id=user.id, title="test")
    session.add(chat_session)
    await session.flush()
    return user.id, chat_session.id


async def _stored(session, storage, chat_session_id, filename="notes.txt", **overrides):
    """Seed a document row and its stored file without going through upload."""
    document = Document(
        chat_session_id=chat_session_id,
        original_filename=filename,
        object_key=f"{chat_session_id}/{uuid.uuid4()}",
        content_type="text/plain",
        size_bytes=len(CONTENT),
        checksum=hashlib.sha256(CONTENT).hexdigest(),
        status=overrides.pop("status", DocumentStatus.UPLOADED),
        **overrides,
    )
    await DocumentRepositoryImpl(session).create(document)
    storage.save(document.object_key, CONTENT)
    return document


async def _row(session, document_id):
    result = await session.execute(
        select(Document.status, Document.size_bytes, Document.checksum).where(
            Document.id == document_id
        )
    )
    return result.one_or_none()


async def _document_count(session, chat_session_id):
    return await DocumentRepositoryImpl(session).count(chat_session_id)


@pytest.fixture
def service(session, object_storage):
    return UploadService(
        document_repository=DocumentRepositoryImpl(session),
        user_repository=UserRepositoryImpl(session),
        chat_session_repository=ChatSessionRepositoryImpl(session),
        object_storage=object_storage,
    )


@pytest_asyncio.fixture
async def owner(session):
    return await _new_owner(session)


class TestUpload:
    async def test_stores_file_and_returns_uploaded_document(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner

        document = await service.upload(chat_session_id, user_id, _file())

        checksum = hashlib.sha256(CONTENT).hexdigest()
        assert document.object_key == f"{chat_session_id}/{document.id}"
        assert object_storage.load(document.object_key) == CONTENT
        assert (await _row(session, document.id)) == (
            DocumentStatus.UPLOADED,
            len(CONTENT),
            checksum,
        )
        assert document.status == DocumentStatus.UPLOADED
        assert document.size_bytes == len(CONTENT)
        assert document.checksum == checksum

    async def test_keeps_only_the_base_filename(self, service, owner):
        user_id, chat_session_id = owner

        document = await service.upload(
            chat_session_id, user_id, _file(filename=r"C:\Users\me/../notes.txt")
        )

        assert document.original_filename == "notes.txt"

    @pytest.mark.parametrize(
        "filename, content_type, expected_status",
        [
            (None, "text/plain", status.HTTP_422_UNPROCESSABLE_CONTENT),
            ("program.exe", "text/plain", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
            ("notes.txt", "image/png", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
        ],
        ids=["no-filename", "bad-extension", "bad-content-type"],
    )
    async def test_rejects_invalid_files_without_storing(
        self, service, session, owner, filename, content_type, expected_status
    ):
        user_id, chat_session_id = owner

        with pytest.raises(ApiException) as exc:
            await service.upload(
                chat_session_id,
                user_id,
                _file(filename=filename, content_type=content_type),
            )

        assert exc.value.status_code == expected_status
        assert await _document_count(session, chat_session_id) == 0

    async def test_rejects_empty_file_and_cleans_up(self, service, session, owner):
        user_id, chat_session_id = owner

        with pytest.raises(ApiException) as exc:
            await service.upload(chat_session_id, user_id, _file(data=b""))

        assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert await _document_count(session, chat_session_id) == 0

    async def test_rejects_oversized_file_and_cleans_up(self, service, session, owner):
        user_id, chat_session_id = owner

        with patch(
            "src.uploads.services.upload_service._MAX_FILE_SIZE_BYTES",
            len(CONTENT) - 1,
        ):
            with pytest.raises(ApiException) as exc:
                await service.upload(chat_session_id, user_id, _file())

        assert exc.value.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        assert await _document_count(session, chat_session_id) == 0

    async def test_rejects_upload_when_session_is_full(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        limit = settings.uploads.MAX_DOCS_PER_SESSION
        for i in range(limit):
            await _stored(session, object_storage, chat_session_id, f"{i}.txt")

        with pytest.raises(ApiException) as exc:
            await service.upload(chat_session_id, user_id, _file(filename="extra.txt"))

        assert exc.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert await _document_count(session, chat_session_id) == limit

    async def test_storage_failure_discards_document(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        failure = object_storage_error(message="down")

        with patch.object(object_storage, "save", side_effect=failure):
            with pytest.raises(ApiException) as exc:
                await service.upload(chat_session_id, user_id, _file())

        assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert await _document_count(session, chat_session_id) == 0

    @pytest.mark.parametrize(
        "caller, expected_status",
        [
            ("unknown-user", status.HTTP_404_NOT_FOUND),
            ("unknown-chat-session", status.HTTP_404_NOT_FOUND),
            ("other-user", status.HTTP_403_FORBIDDEN),
        ],
    )
    async def test_rejects_callers_without_access(
        self, service, session, owner, caller, expected_status
    ):
        user_id, chat_session_id = owner
        if caller == "unknown-user":
            user_id = uuid.uuid4()
        elif caller == "unknown-chat-session":
            chat_session_id = uuid.uuid4()
        else:
            user_id, _ = await _new_owner(session)

        with pytest.raises(ApiException) as exc:
            await service.upload(chat_session_id, user_id, _file())

        assert exc.value.status_code == expected_status
        assert await _document_count(session, owner[1]) == 0


class TestGetUploadedFiles:
    async def test_returns_requested_page_of_viewable_documents(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        for i in range(3):
            await _stored(session, object_storage, chat_session_id, f"{i}.txt")

        page = await service.get_uploaded_files(
            chat_session_id, user_id, Pagination(page=1, limit=2)
        )

        assert page.total == 3
        assert len(page.items) == 2
        assert all(item.chat_session_id == chat_session_id for item in page.items)


class TestGetUploadedFileStatus:
    async def test_returns_status_of_own_document(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        document = await _stored(session, object_storage, chat_session_id)

        result = await service.get_uploaded_file_status(
            chat_session_id, user_id, document.id
        )

        assert result == document.status

    async def test_unknown_or_foreign_document_raises(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        _, other_session = await _new_owner(session)
        foreign = await _stored(session, object_storage, other_session)

        for document_id in (uuid.uuid4(), foreign.id):
            with pytest.raises(ApiException) as exc:
                await service.get_uploaded_file_status(
                    chat_session_id, user_id, document_id
                )
            assert exc.value.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteUploadedFile:
    async def test_removes_row_and_stored_file(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        document = await _stored(session, object_storage, chat_session_id)

        await service.delete_uploaded_file(chat_session_id, user_id, document.id)

        assert await _row(session, document.id) is None
        assert object_storage.exists(document.object_key) is False

    async def test_unknown_document_is_a_no_op(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        survivor = await _stored(session, object_storage, chat_session_id)

        await service.delete_uploaded_file(chat_session_id, user_id, uuid.uuid4())

        assert await _row(session, survivor.id) is not None

    async def test_document_from_another_session_raises_and_is_kept(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        _, other_session = await _new_owner(session)
        foreign = await _stored(session, object_storage, other_session)

        with pytest.raises(ApiException) as exc:
            await service.delete_uploaded_file(chat_session_id, user_id, foreign.id)

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND
        assert await _row(session, foreign.id) is not None
        assert object_storage.exists(foreign.object_key) is True


class TestDeleteUploadedFiles:
    async def test_removes_listed_files_and_skips_the_rest(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        doomed = [
            await _stored(session, object_storage, chat_session_id, f"{i}.txt")
            for i in range(2)
        ]
        unlisted = await _stored(session, object_storage, chat_session_id, "keep.txt")
        _, other_session = await _new_owner(session)
        foreign = await _stored(session, object_storage, other_session)

        deleted = await service.delete_uploaded_files(
            chat_session_id,
            user_id,
            [d.id for d in doomed] + [foreign.id, uuid.uuid4()],
        )

        assert deleted == 2
        assert await _document_count(session, chat_session_id) == 1
        assert not any(object_storage.exists(d.object_key) for d in doomed)
        assert object_storage.exists(unlisted.object_key) is True
        assert await _row(session, foreign.id) is not None
        assert object_storage.exists(foreign.object_key) is True


class TestReprocessUploadedFile:
    async def test_moves_failed_document_back_to_uploaded(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        document = await _stored(
            session, object_storage, chat_session_id, status=DocumentStatus.FAILED
        )

        result = await service.reprocess_uploaded_file(
            chat_session_id, user_id, document.id
        )

        assert result.id == document.id
        assert (await _row(session, document.id)).status == DocumentStatus.UPLOADED

    async def test_document_not_in_failed_state_raises(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        document = await _stored(session, object_storage, chat_session_id)

        with pytest.raises(ApiException) as exc:
            await service.reprocess_uploaded_file(chat_session_id, user_id, document.id)

        assert exc.value.status_code == status.HTTP_409_CONFLICT
        assert (await _row(session, document.id)).status == DocumentStatus.UPLOADED

    async def test_missing_stored_file_raises(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        document = await _stored(
            session, object_storage, chat_session_id, status=DocumentStatus.FAILED
        )
        object_storage.delete(document.object_key)

        with pytest.raises(ApiException) as exc:
            await service.reprocess_uploaded_file(chat_session_id, user_id, document.id)

        assert exc.value.status_code == status.HTTP_409_CONFLICT
        assert (await _row(session, document.id)).status == DocumentStatus.FAILED

    async def test_document_from_another_session_raises(
        self, service, session, object_storage, owner
    ):
        user_id, chat_session_id = owner
        _, other_session = await _new_owner(session)
        foreign = await _stored(session, object_storage, other_session)

        with pytest.raises(ApiException) as exc:
            await service.reprocess_uploaded_file(chat_session_id, user_id, foreign.id)

        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_unknown_document_raises(self, service, owner):
        user_id, chat_session_id = owner

        with pytest.raises(ApiException) as exc:
            await service.reprocess_uploaded_file(
                chat_session_id, user_id, uuid.uuid4()
            )

        assert exc.value.status_code == status.HTTP_404_NOT_FOUND
