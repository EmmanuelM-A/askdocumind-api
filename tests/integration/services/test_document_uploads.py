"""Unit tests for document upload status transitions."""

from io import BytesIO
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import UploadFile

from src.api.services.documents.document_uploads import UploadService
from src.api.services.validation.helper import UploadDocumentsRequest
from src.config.configs import settings
from src.config.constants import ProcessingStatus
from src.errors.api_exceptions import ApiException


def _mock_tx_factory_and_tx():
    tx = Mock()
    tx_cm = AsyncMock()
    tx_cm.__aenter__.return_value = tx
    tx_cm.__aexit__.return_value = None
    tx_factory = Mock()
    tx_factory.create.return_value = tx_cm
    return tx_factory, tx


@pytest.mark.asyncio
async def test_upload_documents_marks_created_documents_completed(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.documents.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.server, "MAX_DOCUMENTS_PER_CHAT", 10)
    monkeypatch.setattr(settings.files, "MAX_FILE_SIZE_MB", 20)

    chat_id = uuid4()
    document_ids = [uuid4(), uuid4()]

    document_repo = Mock()
    document_repo.list_by = AsyncMock(return_value=[])
    document_repo.get_total_size_mb = AsyncMock(return_value=0.0)
    document_repo.create_many = AsyncMock(return_value=document_ids)
    document_repo.bulk_update_processing_status = AsyncMock(return_value=len(document_ids))

    storage = Mock()
    storage.save = Mock()
    storage.delete = Mock()

    vector_processor = Mock()
    vector_processor.process_and_save_vectors_from_uploads = AsyncMock(return_value=None)

    tx_factory, tx = _mock_tx_factory_and_tx()

    service = UploadService(
        storage_service=storage,
        chat_session_repo=Mock(),
        document_repo=document_repo,
        vector_processor=vector_processor,
        tx_factory=tx_factory,
    )

    request = UploadDocumentsRequest(
        chat_id=chat_id,
        documents=[
            UploadFile(filename="a.txt", file=BytesIO(b"a")),
            UploadFile(filename="b.txt", file=BytesIO(b"b")),
        ],
    )

    response = await service.handle_document_uploads(request)

    assert response.success is True
    assert response.message == "Documents uploaded and processed successfully."
    assert response.data["quantity_uploaded"] == 2
    document_repo.bulk_update_processing_status.assert_called_once_with(
        document_ids, ProcessingStatus.COMPLETED, tx=tx
    )
    document_repo.create_many.assert_awaited_once_with(entities=ANY, tx=tx)
    assert tx_factory.create.call_count == 1
    assert document_repo.create_many.await_count == 1
    vector_processor.process_and_save_vectors_from_uploads.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_documents_marks_documents_failed_when_processing_breaks(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.documents.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.server, "MAX_DOCUMENTS_PER_CHAT", 10)
    monkeypatch.setattr(settings.files, "MAX_FILE_SIZE_MB", 20)

    document_repo = Mock()
    document_repo.list_by = AsyncMock(return_value=[])
    document_repo.get_total_size_mb = AsyncMock(return_value=0.0)
    created_ids = [uuid4()]
    document_repo.create_many = AsyncMock(return_value=created_ids)
    document_repo.bulk_update_processing_status = AsyncMock(return_value=1)

    storage = Mock()
    storage.save = Mock()
    storage.delete = Mock()

    vector_processor = Mock()
    vector_processor.process_and_save_vectors_from_uploads = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    tx_factory, _ = _mock_tx_factory_and_tx()

    service = UploadService(
        storage_service=storage,
        chat_session_repo=Mock(),
        document_repo=document_repo,
        vector_processor=vector_processor,
        tx_factory=tx_factory,
    )

    request = UploadDocumentsRequest(
        chat_id=uuid4(),
        documents=[UploadFile(filename="a.txt", file=BytesIO(b"a"))],
    )

    with pytest.raises(ApiException) as exc_info:
        await service.handle_document_uploads(request)

    assert exc_info.value.error.code == "DOCUMENT_METADATA_STORAGE_FAILED"
    assert tx_factory.create.call_count == 1


@pytest.mark.asyncio
async def test_upload_documents_rejects_duplicate_filenames_in_same_request(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.documents.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.server, "MAX_DOCUMENTS_PER_CHAT", 10)

    document_repo = Mock()
    document_repo.count = AsyncMock(return_value=0)
    document_repo.list_by = AsyncMock(return_value=[])

    service = UploadService(
        storage_service=Mock(),
        chat_session_repo=Mock(),
        document_repo=document_repo,
        vector_processor=Mock(),
        tx_factory=Mock(),
    )

    request = UploadDocumentsRequest(
        chat_id=uuid4(),
        documents=[
            UploadFile(filename="dup.txt", file=BytesIO(b"a")),
            UploadFile(filename="DUP.txt", file=BytesIO(b"b")),
        ],
    )

    with pytest.raises(ApiException) as exc_info:
        await service.handle_document_uploads(request)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error.code == "DUPLICATE_DOCUMENTS_IN_REQUEST"


@pytest.mark.asyncio
async def test_upload_documents_rejects_filename_that_already_exists_in_chat(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.documents.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.server, "MAX_DOCUMENTS_PER_CHAT", 10)

    existing_doc = Mock()
    existing_doc.filename = "existing.pdf"

    document_repo = Mock()
    document_repo.count = AsyncMock(return_value=0)
    document_repo.list_by = AsyncMock(return_value=[existing_doc])

    service = UploadService(
        storage_service=Mock(),
        chat_session_repo=Mock(),
        document_repo=document_repo,
        vector_processor=Mock(),
        tx_factory=Mock(),
    )

    request = UploadDocumentsRequest(
        chat_id=uuid4(),
        documents=[UploadFile(filename="Existing.pdf", file=BytesIO(b"a"))],
    )

    with pytest.raises(ApiException) as exc_info:
        await service.handle_document_uploads(request)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error.code == "DOCUMENT_ALREADY_EXISTS"


