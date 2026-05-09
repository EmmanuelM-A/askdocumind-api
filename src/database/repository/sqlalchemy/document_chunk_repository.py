"""
SQLAlchemy concrete implementation of the DocumentChunk repository interface.

This implementation follows patterns used in other repository classes in
`src.database.repository.sqlalchemy` and provides a Python-fallback for
`search_similar` if the database does not provide a vector search operator.
"""

from typing import Optional, List
from uuid import UUID
import math

from sqlalchemy import select, func, delete
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from src.database.connection import DatabaseConnection
from src.database.models import DocumentChunk, Document
from src.database.repository.interfaces.document_chunk_repository import (
    DocumentChunkRepositoryInterface,
    DocumentChunkSearchCriteria,
)
from src.database.repository.interfaces.db_transaction import DBTransaction
from src.errors.custom_exceptions import database_error
from src.logger.base_logger import BaseLogger


class DocumentChunkRepository(DocumentChunkRepositoryInterface):
    """Concrete SQLAlchemy repository for document chunks."""

    def __init__(self, connection: DatabaseConnection) -> None:
        self._db = connection
        self._logger = BaseLogger(__name__)

    @staticmethod
    def _build_filters(criteria: DocumentChunkSearchCriteria) -> list:
        filters = []
        for field, value in criteria.model_dump(exclude_none=True).items():
            filters.append(getattr(DocumentChunk, field) == value)
        return filters

    async def create(
        self, data: DocumentChunk, tx: Optional[DBTransaction] = None
    ) -> UUID:
        try:
            if tx is not None:
                await tx.add(data)
                await tx.flush()
                self._logger.debug(f"New chunk created: {data.id}")
                return data.id

            async with self._db.get_session() as session:
                session.add(data)
                await session.flush()
                self._logger.debug(f"New chunk created: {data.id}")
                return data.id

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while creating a document chunk.",
                error_code="DOCUMENT_CHUNK_CREATION_ERROR",
                stack_trace=str(e),
            )

    async def list_by(
        self,
        criteria: Optional[DocumentChunkSearchCriteria] = None,
        tx: Optional[DBTransaction] = None,
    ) -> List[DocumentChunk]:
        try:
            stmt = select(DocumentChunk)

            if criteria is not None:
                stmt = stmt.where(*self._build_filters(criteria))

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalars().all()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalars().all()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while listing document chunks.",
                error_code="DOCUMENT_CHUNK_LISTING_ERROR",
                stack_trace=str(e),
            )

    async def get_by_id(
        self, chunk_id: UUID, tx: Optional[DBTransaction] = None
    ) -> Optional[DocumentChunk]:
        try:
            stmt = select(DocumentChunk).where(DocumentChunk.id == chunk_id)

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalar_one_or_none()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalar_one_or_none()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting document chunk by id.",
                error_code="DOCUMENT_CHUNK_GET_ERROR",
                stack_trace=str(e),
            )

    async def get_by_criteria(
        self, criteria: DocumentChunkSearchCriteria, tx: Optional[DBTransaction] = None
    ) -> Optional[DocumentChunk]:
        try:
            filters = self._build_filters(criteria)

            if not filters:
                return None

            stmt = select(DocumentChunk).where(*filters)

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalars().first()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalars().first()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while getting document chunk by criteria.",
                error_code="DOCUMENT_CHUNK_GET_ERROR",
                stack_trace=str(e),
            )

    async def list_by_document_id(
        self, document_id: UUID, tx: Optional[DBTransaction] = None
    ) -> List[DocumentChunk]:
        return await self.list_by(
            DocumentChunkSearchCriteria(document_id=document_id), tx=tx
        )

    async def upsert_many(
        self, chunks: List[DocumentChunk], tx: Optional[DBTransaction] = None
    ) -> List[UUID]:
        if not chunks:
            return []

        try:
            if tx is not None:
                await tx.add_all(chunks)
                await tx.flush()
                return [c.id for c in chunks]

            async with self._db.get_session() as session:
                session.add_all(chunks)
                await session.flush()
                return [c.id for c in chunks]

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while upserting document chunks.",
                error_code="DOCUMENT_CHUNK_UPSERT_ERROR",
                stack_trace=str(e),
            )

    async def delete(self, chunk_id: UUID, tx: Optional[DBTransaction] = None) -> bool:
        try:
            stmt = delete(DocumentChunk).where(DocumentChunk.id == chunk_id)

            if tx is not None:
                result = await tx.execute(stmt)
                return (result.rowcount or 0) > 0

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return (result.rowcount or 0) > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting document chunk.",
                error_code="DOCUMENT_CHUNK_DELETE_ERROR",
                stack_trace=str(e),
            )

    async def delete_by_document_id(
        self, document_id: UUID, tx: Optional[DBTransaction] = None
    ) -> int:
        try:
            stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)

            if tx is not None:
                result = await tx.execute(stmt)
                return result.rowcount or 0

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.rowcount or 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while deleting document chunks by document id.",
                error_code="DOCUMENT_CHUNK_DELETE_ERROR",
                stack_trace=str(e),
            )

    async def exists(self, chunk_id: UUID, tx: Optional[DBTransaction] = None) -> bool:
        try:
            stmt = (
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.id == chunk_id)
            )

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalar_one() > 0

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalar_one() > 0

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while checking chunk existence.",
                error_code="DOCUMENT_CHUNK_EXISTS_ERROR",
                stack_trace=str(e),
            )

    async def count(
        self, document_id: Optional[UUID] = None, tx: Optional[DBTransaction] = None
    ) -> int:
        try:
            stmt = select(func.count(DocumentChunk.id)).select_from(DocumentChunk)
            if document_id:
                stmt = stmt.where(DocumentChunk.document_id == document_id)

            if tx is not None:
                result = await tx.execute(stmt)
                return result.scalar_one()

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                return result.scalar_one()

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while counting document chunks.",
                error_code="DOCUMENT_CHUNK_COUNT_ERROR",
                stack_trace=str(e),
            )

    async def _get_similarity_candidates(
        self,
        chat_session_id: UUID,
        tx: Optional[DBTransaction] = None,
    ) -> List[DocumentChunk]:
        stmt = select(DocumentChunk).where(
            DocumentChunk.chat_session_id == chat_session_id
        )

        if tx is not None:
            result = await tx.execute(stmt)
            return result.scalars().all()

        async with self._db.get_session() as session:
            result = await session.execute(stmt)
            return result.scalars().all()

    async def search_similar(
        self,
        chat_session_id: UUID,
        vector: List[float],
        top_k: int = 10,
        threshold: Optional[float] = None,
        tx: Optional[DBTransaction] = None,
    ) -> List[DocumentChunk]:
        """
        Fallback similarity search implementation.

        This implementation attempts to perform a Python-side similarity search
        if a DB-level vector operator is not available. For small datasets or
        tests this is acceptable; for production use pgvector/FAISS-backed
        implementations should override this for efficiency.
        """
        candidates = await self._get_similarity_candidates(
            chat_session_id=chat_session_id,
            tx=tx,
        )

        if vector is None:
            return []

        vector_norm = math.sqrt(sum(x * x for x in vector))
        if vector_norm == 0:
            return []

        scored = []
        for c in candidates:
            emb = c.embedding
            if emb is None:
                continue

            try:
                if hasattr(emb, "tolist"):
                    emb_list = emb.tolist()
                elif isinstance(emb, (list, tuple)):
                    emb_list = list(emb)
                else:
                    continue
            except Exception:
                continue

            emb_norm = math.sqrt(sum(x * x for x in emb_list))
            if emb_norm == 0:
                continue

            score = sum(x * y for x, y in zip(vector, emb_list)) / (
                vector_norm * emb_norm
            )

            if threshold is not None and score < threshold:
                continue
            scored.append((score, c))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [t[1] for t in scored[:top_k]]

    async def get_filenames_for_chunks(
        self,
        chunks: List[DocumentChunk],
        chat_session_id: UUID,
        tx: Optional[DBTransaction] = None,
    ) -> List[str]:
        """
        Retrieves unique filenames for all documents associated with the given chunks.
        Results are filtered to only include documents from the specified chat_session_id.
        """
        if not chunks:
            return []

        try:
            # Extract unique document IDs from chunks
            document_ids = set(chunk.document_id for chunk in chunks)

            # Query documents where id IN (extracted IDs) AND session_id matches
            stmt = select(Document.filename).where(
                (Document.id.in_(document_ids)) & (Document.session_id == chat_session_id)
            )

            if tx is not None:
                result = await tx.execute(stmt)
                filenames = result.scalars().unique().all()
                self._logger.debug(f"Retrieved {len(filenames)} unique filenames for chunks")
                return filenames

            async with self._db.get_session() as session:
                result = await session.execute(stmt)
                filenames = result.scalars().unique().all()
                self._logger.debug(f"Retrieved {len(filenames)} unique filenames for chunks")
                return filenames

        except (IntegrityError, SQLAlchemyError, Exception) as e:
            raise database_error(
                message="An error occurred while retrieving filenames for chunks.",
                error_code="DOCUMENT_CHUNK_FILENAMES_ERROR",
                stack_trace=str(e),
            )


