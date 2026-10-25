"""
Unit tests for the per session document limit in UploadService.upload.
"""

import io
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

import src.database.models  # noqa: F401  registers every model for the mappers
from src.config.configs import settings
from src.exceptions.base import ApiException
from src.uploads.services.upload_service import UploadService

pytestmark = pytest.mark.asyncio

USER_ID = uuid.uuid4()
CHAT_SESSION_ID = uuid.uuid4()
LIMIT = settings.uploads.MAX_DOCS_PER_SESSION


@pytest.fixture
def document_repository():
    repository = AsyncMock()
    repository.mark_uploaded.return_value = True
    repository.get_by_id.return_value = SimpleNamespace(id=uuid.uuid4())
    return repository


@pytest.fixture
def service(document_repository):
    user_repository = AsyncMock()
    user_repository.get_by_id.return_value = SimpleNamespace(id=USER_ID)
    chat_session_repository = AsyncMock()
    chat_session_repository.get_by_id.return_value = SimpleNamespace(user_id=USER_ID)

    return UploadService(
        document_repository=document_repository,
        user_repository=user_repository,
        chat_session_repository=chat_session_repository,
        object_storage=MagicMock(),
    )


def _file():
    return UploadFile(
        file=io.BytesIO(b"hello"),
        filename="notes.txt",
        headers=Headers({"content-type": "text/plain"}),
    )


@pytest.mark.parametrize("existing", [LIMIT, LIMIT + 1], ids=["at-limit", "over-limit"])
async def test_upload_is_rejected_when_session_is_full(
    service, document_repository, existing
):
    document_repository.count.return_value = existing

    with pytest.raises(ApiException) as exc:
        await service.upload(CHAT_SESSION_ID, USER_ID, _file())

    assert exc.value.error_code == "MAX_DOCUMENTS_REACHED"
    document_repository.count.assert_awaited_once_with(CHAT_SESSION_ID)
    document_repository.create.assert_not_awaited()


async def test_upload_below_limit_is_stored(service, document_repository):
    document_repository.count.return_value = LIMIT - 1

    await service.upload(CHAT_SESSION_ID, USER_ID, _file())

    document_repository.create.assert_awaited_once()
