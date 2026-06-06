"""Unit tests for anonymous-session resource limit guards."""

from io import BytesIO
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from fastapi import UploadFile
import pytest
from starlette.requests import Request

from src.api.middleware.rate_limiter import (
    chat_query_limit,
    user_key_func,
)
from src.api.services.chats.chat_sessions import ChatSessionService
from src.api.services.documents.document_uploads import UploadService
from src.api.services.validation.rag_validation import UploadDocumentsRequest
from src.api.services.validation.schemas import CreateChatSchema
from src.config.configs import settings
from src.errors.api_exceptions import ApiException


@pytest.mark.asyncio
async def test_create_chat_blocks_when_anonymous_chat_limit_is_reached(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "src.api.services.chat_sessions.require_current_anonymous_user_id",
        lambda: uuid4(),
    )
    monkeypatch.setattr(settings.server, "MAX_CHATS_PER_USER", 2)

    chat_session_repo = Mock()
    chat_session_repo.list_by = AsyncMock(return_value=[Mock(), Mock()])

    service = ChatSessionService(
        chatbot=Mock(),
        storage=Mock(),
        chat_session_repo=chat_session_repo,
        chat_message_repo=Mock(),
        tx_factory=Mock(),
    )

    with pytest.raises(ApiException) as exc_info:
        await service.create_new_chat(CreateChatSchema(title="limit"))

    assert exc_info.value.status_code == 422
    assert exc_info.value.error.code == "MAX_CHATS_PER_USER_REACHED"


@pytest.mark.asyncio
async def test_upload_blocks_when_per_chat_document_limit_is_exceeded(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.server, "MAX_DOCUMENTS_PER_CHAT", 2)

    document_repo = Mock()
    document_repo.count = AsyncMock(return_value=1)
    document_repo.list_by = AsyncMock(return_value=[])
    document_repo.create_many = AsyncMock()

    storage = Mock()
    service = UploadService(
        storage_service=storage,
        chat_session_repo=Mock(),
        document_repo=document_repo,
        chatbot=Mock(),
        tx_factory=Mock(),
    )

    request = UploadDocumentsRequest(
        chat_id=uuid4(),
        documents=[
            UploadFile(filename="a.txt", file=BytesIO(b"a")),
            UploadFile(filename="b.txt", file=BytesIO(b"b")),
        ],
    )

    with pytest.raises(ApiException) as exc_info:
        await service.handle_document_uploads(request)

    assert exc_info.value.status_code == 422
    assert exc_info.value.error.code == "CHAT_DOCUMENT_LIMIT_REACHED"
    assert not storage.save.called
    document_repo.create_many.assert_not_called()


@pytest.mark.asyncio
async def test_upload_blocks_when_file_size_limit_is_exceeded(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.server, "MAX_DOCUMENTS_PER_CHAT", 10)
    monkeypatch.setattr(settings.files, "MAX_FILE_SIZE_MB", 1)

    document_repo = Mock()
    document_repo.count = AsyncMock(return_value=0)
    document_repo.list_by = AsyncMock(return_value=[])
    document_repo.create_many = AsyncMock()

    storage = Mock()
    service = UploadService(
        storage_service=storage,
        chat_session_repo=Mock(),
        document_repo=document_repo,
        chatbot=Mock(),
        tx_factory=Mock(),
    )

    oversized_bytes = b"x" * (1024 * 1024 + 1)
    request = UploadDocumentsRequest(
        chat_id=uuid4(),
        documents=[UploadFile(filename="large.txt", file=BytesIO(oversized_bytes))],
    )

    with pytest.raises(ApiException) as exc_info:
        await service.handle_document_uploads(request)

    assert (
        exc_info.value.status_code == 500
    )  # TODO: REFACTORING NEEDED IN DOC UPLOAD SERVICE TO RAISE 422 IN THIS CASE
    assert exc_info.value.error.code == "DOCUMENT_READ_FAILED"
    assert not storage.save.called
    document_repo.create_many.assert_not_called()


def test_anonymous_session_rate_limit_key_prefers_session_id():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/chat",
            "headers": [],
            "client": ("127.0.0.1", 9999),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )

    session_user_id = uuid4()
    request.state.anonymous_user_id = session_user_id

    assert user_key_func(request) == f"anon:{session_user_id}"


def test_anonymous_session_rate_limit_key_falls_back_to_ip():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/chat",
            "headers": [],
            "client": ("127.0.0.1", 9999),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )

    assert user_key_func(request) == "127.0.0.1"


def test_anonymous_chat_query_limit_uses_server_setting(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings.server, "MAX_CHAT_QUERIES_PER_MINUTE", 17)

    assert chat_query_limit() == "17/minute"
