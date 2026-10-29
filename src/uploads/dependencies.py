from typing import Annotated

from fastapi import Request
from fastapi.params import Depends

from src.auth.dependencies import get_user_repository
from src.auth.repository.user_repository import UserRepository
from src.chat_session.dependencies import get_chat_session_repository
from src.chat_session.repository.chat_session_repository import ChatSessionRepository
from src.database.dependencies import DbSession
from src.uploads.repository.document_repository import DocumentRepository
from src.uploads.repository.document_repository_impl import DocumentRepositoryImpl
from src.uploads.services.ingestion_service import IngestionRunner
from src.uploads.services.upload_service import UploadService
from src.uploads.storage.dependencies import get_object_storage
from src.uploads.storage.object_storage import ObjectStorage


def get_document_repository(session: DbSession) -> DocumentRepository:
    """
    Provide a DocumentRepository bound to the current request's session.
    """
    return DocumentRepositoryImpl(session)


def get_upload_service(
    document_repository: Annotated[
        DocumentRepository, Depends(get_document_repository)
    ],
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    chat_session_repository: Annotated[
        ChatSessionRepository, Depends(get_chat_session_repository)
    ],
    object_storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> UploadService:
    """
    Provide an UploadService instance for the current request.
    """
    return UploadService(
        document_repository=document_repository,
        user_repository=user_repository,
        chat_session_repository=chat_session_repository,
        object_storage=object_storage,
    )


def get_ingestion_runner(request: Request) -> IngestionRunner:
    return request.app.state.ingestion_runner
