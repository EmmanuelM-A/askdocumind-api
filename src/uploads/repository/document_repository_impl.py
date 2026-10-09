import logging
from uuid import UUID

from fastapi_pagination import Page
from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.utils import BaseRepository, Pagination
from src.exceptions import database_error
from src.uploads import Document
from src.uploads.domain.document import DocumentStatus
from src.uploads.repository.document_repository import (
    DocumentRepository,
    DocumentSearchFilter,
)

_logger = logging.getLogger(__name__)


def _apply_filter(
    chat_session_id: UUID, criteria: DocumentSearchFilter | None
) -> Select:
    """Select documents for a chat session, narrowed by the optional criteria."""
    statement = select(Document).where(Document.chat_session_id == chat_session_id)

    if criteria is None:
        return statement

    if criteria.filename is not None:
        statement = statement.where(
            Document.original_filename.icontains(criteria.filename, autoescape=True)
        )
    if criteria.status is not None:
        statement = statement.where(Document.status == criteria.status)

    return statement


class DocumentRepositoryImpl(BaseRepository, DocumentRepository):
    """Concrete implementation of the DocumentRepository interface."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def create(self, data: Document) -> Document:
        try:
            self._session.add(data)
            await self._session.flush()
            return data
        except Exception as e:
            raise database_error(
                message="An error occurred while creating a document.",
                error_code="DOCUMENT_CREATION_ERROR",
                cause=e,
            ) from e

    async def create_many(self, entities: list[Document]) -> list[UUID]:
        if not entities:
            return []
        try:
            self._session.add_all(entities)
            await self._session.flush()
            return [entity.id for entity in entities]
        except Exception as e:
            raise database_error(
                message="An error occurred while creating documents.",
                error_code="DOCUMENT_CREATION_ERROR",
                cause=e,
            ) from e

    async def list_by_criteria(
        self, chat_session_id: UUID, criteria: DocumentSearchFilter | None = None
    ) -> list[Document]:
        statement = _apply_filter(chat_session_id, criteria).order_by(
            Document.created_at.desc(), Document.id.desc()
        )
        try:
            result = await self._session.execute(statement)
            return list(result.scalars().all())
        except Exception as e:
            raise database_error(
                message="An error occurred while listing documents.",
                error_code="DOCUMENT_FETCH_ERROR",
                cause=e,
            ) from e

    async def list_by_criteria_paginated(
        self,
        chat_session_id: UUID,
        paginate: Pagination,
        criteria: DocumentSearchFilter | None = None,
    ) -> Page[Document]:
        statement = _apply_filter(chat_session_id, criteria).order_by(
            Document.created_at.desc(), Document.id.desc()
        )
        try:
            return await self._paginate(statement, paginate)
        except Exception as e:
            raise database_error(
                message="An error occurred while listing documents with pagination.",
                error_code="DOCUMENT_FETCH_ERROR",
                cause=e,
            ) from e

    async def get_by_id(self, document_id: UUID) -> Document | None:
        statement = select(Document).where(Document.id == document_id)
        try:
            result = await self._session.execute(statement)
            return result.scalar_one_or_none()
        except Exception as e:
            raise database_error(
                message="An error occurred while fetching a document by ID.",
                error_code="DOCUMENT_FETCH_ERROR",
                cause=e,
            ) from e

    async def count(self, chat_session_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(Document)
            .where(Document.chat_session_id == chat_session_id)
        )
        try:
            return (await self._session.execute(statement)).scalar_one()
        except Exception as e:
            raise database_error(
                message="An error occurred while counting documents.",
                error_code="DOCUMENT_FETCH_ERROR",
                cause=e,
            ) from e

    async def delete(self, document_id: UUID) -> None:
        statement = delete(Document).where(Document.id == document_id)
        try:
            result = await self._session.execute(statement)
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting a document.",
                error_code="DOCUMENT_DELETION_ERROR",
                cause=e,
            ) from e

        if result.rowcount == 0:
            raise database_error(
                message="Document not found for deletion.",
                error_code="DOCUMENT_NOT_FOUND",
            )

    async def delete_many(self, document_ids: list[UUID]) -> int:
        if not document_ids:
            return 0

        statement = delete(Document).where(Document.id.in_(document_ids))
        try:
            result = await self._session.execute(statement)
            return result.rowcount
        except Exception as e:
            raise database_error(
                message="An error occurred while deleting documents.",
                error_code="DOCUMENT_DELETION_ERROR",
                cause=e,
            ) from e

    async def update_document_status(
        self, document_id: UUID, new_status: DocumentStatus
    ) -> None:
        statement = (
            update(Document).where(Document.id == document_id).values(status=new_status)
        )
        try:
            result = await self._session.execute(statement)
        except Exception as e:
            raise database_error(
                message="An error occurred while updating the document status.",
                error_code="DOCUMENT_UPDATE_ERROR",
                cause=e,
            ) from e

        if result.rowcount == 0:
            raise database_error(
                message="Document not found for status update.",
                error_code="DOCUMENT_NOT_FOUND",
            )
