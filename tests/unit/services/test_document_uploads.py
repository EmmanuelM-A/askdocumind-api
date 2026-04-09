"""Unit tests for document upload status transitions."""

from io import BytesIO
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import UploadFile

from src.api.services.document_uploads import UploadService
from src.api.services.validation.rag_validation import UploadDocumentsRequest
from src.config.configs import settings
from src.config.constants import ProcessingStatus
from src.errors.api_exceptions import ApiException


@pytest.mark.asyncio
async def test_upload_documents_marks_created_documents_completed(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.server, "MAX_DOCUMENTS_PER_CHAT", 10)
    monkeypatch.setattr(settings.files, "MAX_FILE_SIZE_MB", 20)

    chat_id = uuid4()
    document_ids = [uuid4(), uuid4()]

    document_repo = Mock()
    document_repo.count = AsyncMock(return_value=0)
    document_repo.create_many = AsyncMock(return_value=document_ids)
    document_repo.bulk_update_processing_status = AsyncMock(return_value=len(document_ids))

    storage = Mock()
    storage.save = Mock()
    storage.delete = Mock()

    chatbot = Mock()
    chatbot.process_and_save_vectors = Mock(return_value=None)

    service = UploadService(
        storage_service=storage,
        chat_session_repo=Mock(),
        document_repo=document_repo,
        chatbot=chatbot,
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
        document_ids, ProcessingStatus.COMPLETED
    )
    assert document_repo.create_many.await_count == 1
    assert chatbot.process_and_save_vectors.call_count == 1


@pytest.mark.asyncio
async def test_upload_documents_marks_documents_failed_when_processing_breaks(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.server, "MAX_DOCUMENTS_PER_CHAT", 10)
    monkeypatch.setattr(settings.files, "MAX_FILE_SIZE_MB", 20)

    document_repo = Mock()
    document_repo.count = AsyncMock(return_value=0)
    document_repo.create_many = AsyncMock(return_value=[])
    document_repo.bulk_update_processing_status = AsyncMock(return_value=0)

    storage = Mock()
    storage.save = Mock()
    storage.delete = Mock()

    chatbot = Mock()
    chatbot.process_and_save_vectors = Mock(side_effect=RuntimeError("boom"))

    service = UploadService(
        storage_service=storage,
        chat_session_repo=Mock(),
        document_repo=document_repo,
        chatbot=chatbot,
    )

    request = UploadDocumentsRequest(
        chat_id=uuid4(),
        documents=[UploadFile(filename="a.txt", file=BytesIO(b"a"))],
    )

    with pytest.raises(ApiException) as exc_info:
        await service.handle_document_uploads(request)

    assert exc_info.value.error.code == "VECTOR_PROCESSING_FAILED"
    args, _ = document_repo.bulk_update_processing_status.call_args
    assert len(args[0]) == 1
    assert args[1] == ProcessingStatus.FAILED


