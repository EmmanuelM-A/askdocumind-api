"""Tests for anonymous-session resource limit guards."""

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
from src.api.services.documents.document_uploads import UploadDocumentService
from src.api.services.validation.chat_session import CreateChatSessionData
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


@pytest.mark.asyncio
async def test_create_chat_blocks_when_anonymous_chat_limit_is_reached(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings.app, "MAX_CHATS_PER_USER", 2)

    chat_session_repo = Mock()
    chat_session_repo.list_by = AsyncMock(return_value=[Mock(), Mock()])

    service = ChatSessionService(
        chat_session_repo=chat_session_repo,
        chat_message_repo=Mock(),
    )

    with pytest.raises(ApiException) as exc_info:
        await service.create_new_chat(
            owner_id=uuid4(),
            data=CreateChatSessionData(title="limit"),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.error.code == "MAX_CHATS_PER_USER_REACHED"


@pytest.mark.asyncio
async def test_upload_blocks_when_per_chat_document_limit_is_exceeded(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.documents.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.files, "MAX_FILES_PER_CHAT_MB", 2)

    document_repo = Mock()
    document_repo.list_by = AsyncMock(return_value=[])
    document_repo.get_total_size_mb = AsyncMock(return_value=2.0)
    document_repo.create_many = AsyncMock()

    tx_factory, _ = _mock_tx_factory_and_tx()

    service = UploadDocumentService(
        vector_processor=Mock(),
        chat_session_repo=Mock(),
        document_repo=document_repo,
        tx_factory=tx_factory,
    )

    request = UploadDocumentsRequest(
        chat_id=uuid4(),
        documents=[
            UploadFile(filename="a.txt", file=BytesIO(b"a")),
            UploadFile(filename="b.txt", file=BytesIO(b"b")),
        ],
    )

    with pytest.raises(ApiException) as exc_info:
        await service.handle_document_uploads(owner_id=uuid4(), request=request)

    assert exc_info.value.status_code == 409
    assert exc_info.value.error.code == "ALL_DOCUMENTS_EXCEED_CHAT_LIMIT"
    document_repo.create_many.assert_not_called()


@pytest.mark.asyncio
async def test_upload_blocks_when_file_size_limit_is_exceeded(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _chat_exists(**kwargs):
        return None

    monkeypatch.setattr(
        "src.api.services.documents.document_uploads.check_if_chat_exists", _chat_exists
    )
    monkeypatch.setattr(settings.files, "MAX_FILE_SIZE_MB", 1)

    document_repo = Mock()
    document_repo.list_by = AsyncMock(return_value=[])
    document_repo.get_total_size_mb = AsyncMock(return_value=0.0)
    document_repo.create_many = AsyncMock()

    tx_factory, _ = _mock_tx_factory_and_tx()

    service = UploadDocumentService(
        vector_processor=Mock(),
        chat_session_repo=Mock(),
        document_repo=document_repo,
        tx_factory=tx_factory,
    )

    oversized_bytes = b"x" * (1024 * 1024 + 1)
    request = UploadDocumentsRequest(
        chat_id=uuid4(),
        documents=[UploadFile(filename="large.txt", file=BytesIO(oversized_bytes))],
    )

    with pytest.raises(ApiException) as exc_info:
        await service.handle_document_uploads(owner_id=uuid4(), request=request)

    assert exc_info.value.status_code == 422
    assert exc_info.value.error.code == "FILE_SIZE_LIMIT_EXCEEDED"
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
