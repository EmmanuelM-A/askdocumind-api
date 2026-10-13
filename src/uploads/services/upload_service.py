import hashlib
import logging
from asyncio import to_thread
from pathlib import PureWindowsPath
from uuid import UUID, uuid4

from fastapi import UploadFile

from src.auth.repository.user_repository import UserRepository
from src.chat_session.repository.chat_session_repository import ChatSessionRepository
from src.config.configs import settings
from src.exceptions import (
    unprocessable_content_error,
    unsupported_media_type_error,
    content_too_large_error,
    conflict_error,
    not_found_error,
    forbidden_error,
)
from src.uploads.models.document import Document
from src.uploads.repository.document_repository import DocumentRepository
from src.uploads.storage.object_storage import ObjectStorage

_logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = (
    settings.uploads.ALLOWED_EXTENSIONS + settings.uploads.ALLOWED_CODE_EXTENSIONS,
)

_ALLOWED_CONTENT_TYPES = settings.uploads.ALLOWED_CONTENT_TYPES

_MAX_FILE_SIZE_BYTES = settings.uploads.MAX_FILE_SIZE_MB * 1024 * 1024


async def _read_from(file: UploadFile) -> tuple[bytes, int, str]:
    """
    Reads the content of the uploaded file and calculates its size and checksum.
    """
    hasher, buffer = hashlib.sha256(), bytearray()

    while block := await file.read(size=settings.uploads.BLOCK_SIZE_TO_READ_BYTES):
        if len(buffer) + len(block) > _MAX_FILE_SIZE_BYTES:
            raise content_too_large_error(
                message="The file provided is too large.",
                error_code="FILE_TOO_LARGE",
            )
        buffer += block
        hasher.update(block)

        if not buffer:
            raise unprocessable_content_error(
                message="The file provided is empty.",
                error_code="EMPTY_FILE",
            )

    return bytes(buffer), len(buffer), hasher.hexdigest()


class UploadService:

    def __init__(
        self,
        document_repository: DocumentRepository,
        user_repository: UserRepository,
        chat_session_repository: ChatSessionRepository,
        object_storage: ObjectStorage,
    ) -> None:
        self._document_repository = document_repository
        self._user_repository = user_repository
        self._chat_session_repository = chat_session_repository
        self._object_storage = object_storage

    async def upload(
        self, chat_session_id: UUID, user_id: UUID, file: UploadFile
    ) -> Document:
        user = await self._user_repository.get_by_id(user_id)

        if user is None:
            raise not_found_error(
                message="The user provided does not exist.",
                error_code="USER_NOT_FOUND",
            )

        chat_session = await self._chat_session_repository.get_by_id(chat_session_id)

        if chat_session is None:
            raise not_found_error(
                message="The chat session provided does not exist.",
                error_code="CHAT_SESSION_NOT_FOUND",
            )

        if chat_session.user_id != user_id:
            raise forbidden_error(
                message="The user does not have permission to upload files "
                "to this chat session.",
                error_code="UPLOAD_DENIED",
            )

        if not file.filename:
            raise unprocessable_content_error(
                message="The file provided has no filename.",
                error_code="MISSING_FILENAME",
            )

        filename = PureWindowsPath(file.filename).name

        if not filename or filename.strip() == "" or len(filename) > 255:
            raise unprocessable_content_error(
                message="The filename provided is invalid.",
                error_code="INVALID_FILENAME",
            )

        extension = filename.split(".")[-1].lower()

        if extension not in _ALLOWED_EXTENSIONS:
            raise unsupported_media_type_error(
                message="The file provided has an unsupported file extension.",
                error_code="UNSUPPORTED_FILE_EXTENSION",
            )

        if not file.content_type or file.content_type not in _ALLOWED_CONTENT_TYPES:
            raise unsupported_media_type_error(
                message="The file provided has an unsupported content type.",
                error_code="UNSUPPORTED_CONTENT_TYPE",
            )

        docs_uploaded_so_far = await self._document_repository.count(chat_session_id)

        if docs_uploaded_so_far >= settings.uploads.MAX_DOCUMENTS_PER_SESSION:
            raise unprocessable_content_error(
                message="The maximum number of documents for this session has "
                "been reached.",
                error_code="MAX_DOCUMENTS_REACHED",
            )

        document_id = uuid4()
        key = f"{chat_session_id}/{document_id}"

        await self._document_repository.create(
            Document(
                id=document_id,
                chat_session_id=chat_session_id,
                original_filename=filename,
                object_key=key,
                content_type=file.content_type,
                size_bytes=0,
            )
        )

        try:
            data, size, checksum = await _read_from(file)
            await to_thread(self._object_storage.save, key, data)
            uploaded = await self._document_repository.mark_uploaded(
                document_id=document_id, size_bytes=size, checksum=checksum
            )

            if not uploaded:
                raise conflict_error(
                    message="The file provided has not been uploaded.",
                    error_code="UPLOAD_FAILED",
                )
        except Exception as exc:
            await self._discard_file(document_id, key)
            raise exc

        created = await self._document_repository.get_by_id(document_id)

        if not created:
            raise conflict_error(
                message="The file provided has not been uploaded.",
                error_code="UPLOAD_FAILED",
            )

        return created

    async def _discard_file(self, document_id: UUID, key: str) -> None:
        """
        Discards a file by deleting it from the object storage and
        removing its metadata from the document repository. If an error
        occurs during the process, it logs the exception.
        """
        try:
            await to_thread(self._object_storage.delete, key)
            await self._document_repository.delete(document_id)
        except Exception as exc:
            _logger.exception(
                "Failed to discard the file with the key '%s' and document ID '%s'.",
                key,
                document_id,
                exc_info=exc,
            )
