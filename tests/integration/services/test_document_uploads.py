"""Tests for document upload service."""

from io import BytesIO
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import UploadFile

from src.api.services.documents.document_uploads import UploadDocumentService
from src.api.services.validation.document import UploadDocumentsRequest
from src.config.configs import settings
from src.errors.api_exceptions import ApiException


def _mock_tx_factory_and_tx():
    tx = Mock()
    tx_cm = AsyncMock()
    tx_cm.__aenter__.return_value = tx
    tx_cm.__aexit__.return_value = None
    tx_factory = Mock()
    tx_factory.create.return_value = tx_cm
    return tx_factory, tx


def _make_service(*, document_repo=None, vector_processor=None, tx_factory=None):
    return UploadDocumentService(
        vector_processor=vector_processor or Mock(),
        chat_session_repo=Mock(),
        document_repo=document_repo or Mock(),
        tx_factory=tx_factory or Mock(),
    )


@pytest.mark.asyncio
async def test_upload_documents_returns_count_of_created_documents(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.documents.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.files, "MAX_FILE_SIZE_MB", 20)

    chat_id = uuid4()
    document_ids = [uuid4(), uuid4()]

    document_repo = Mock()
    document_repo.list_by = AsyncMock(return_value=[])
    document_repo.get_total_size_mb = AsyncMock(return_value=0.0)
    document_repo.create_many = AsyncMock(return_value=document_ids)
    document_repo.bulk_update_processing_status = AsyncMock(return_value=len(document_ids))

    vector_processor = Mock()
    vector_processor.process_and_save_vectors_from_uploads = AsyncMock(return_value=None)

    tx_factory, tx = _mock_tx_factory_and_tx()

    service = _make_service(
        document_repo=document_repo,
        vector_processor=vector_processor,
        tx_factory=tx_factory,
    )

    owner_id = uuid4()
    request = UploadDocumentsRequest(
        chat_id=chat_id,
        documents=[
            UploadFile(filename="a.txt", file=BytesIO(b"a")),
            UploadFile(filename="b.txt", file=BytesIO(b"b")),
        ],
    )

    count = await service.handle_document_uploads(owner_id=owner_id, request=request)

    assert count == 2
    document_repo.bulk_update_processing_status.assert_called_once_with(
        document_ids=document_ids, status=ANY, tx=tx
    )
    document_repo.create_many.assert_awaited_once_with(entities=ANY, tx=tx)
    assert tx_factory.create.call_count == 1
    vector_processor.process_and_save_vectors_from_uploads.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_documents_rejects_duplicate_filenames_in_same_request(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.documents.document_uploads.check_if_chat_exists", _chat_exists
    )

    document_repo = Mock()
    document_repo.list_by = AsyncMock(return_value=[])

    service = _make_service(document_repo=document_repo)

    request = UploadDocumentsRequest(
        chat_id=uuid4(),
        documents=[
            UploadFile(filename="dup.txt", file=BytesIO(b"a")),
            UploadFile(filename="DUP.txt", file=BytesIO(b"b")),
        ],
    )

    with pytest.raises(ApiException) as exc_info:
        await service.handle_document_uploads(owner_id=uuid4(), request=request)

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

    existing_doc = Mock()
    existing_doc.filename = "existing.pdf"

    document_repo = Mock()
    document_repo.list_by = AsyncMock(return_value=[existing_doc])

    service = _make_service(document_repo=document_repo)

    request = UploadDocumentsRequest(
        chat_id=uuid4(),
        documents=[UploadFile(filename="Existing.pdf", file=BytesIO(b"a"))],
    )

    with pytest.raises(ApiException) as exc_info:
        await service.handle_document_uploads(owner_id=uuid4(), request=request)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error.code == "DOCUMENT_ALREADY_EXISTS"
