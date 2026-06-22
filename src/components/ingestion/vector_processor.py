from typing import List, Optional, Tuple
from uuid import UUID

from src.config.configs import settings
from src.components.ingestion.document_processor import (
    UploadedDocumentProcessor,
    WebDocumentProcessor,
)
from src.components.retrieval.embedder import Embedder
from src.database.models import DocumentChunk
from src.database.repository.interfaces import DBTransaction
from src.database.repository.interfaces.document_chunk_repository import (
    DocumentChunkRepositoryInterface,
)
from src.logger.base_logger import BaseLogger


class VectorProcessor:
    def __init__(
        self,
        upload_document_processor: UploadedDocumentProcessor,
        web_document_processor: WebDocumentProcessor,
        embedder: Embedder,
        document_chunk_repository: DocumentChunkRepositoryInterface,
    ):
        self._upload_document_processor = upload_document_processor
        self._web_document_processor = web_document_processor
        self._embedder = embedder
        self._document_chunk_repository = document_chunk_repository
        self._logger = BaseLogger(__name__)

    async def process_and_save_vectors_from_uploads(
        self,
        chat_session_id: UUID,
        documents: List[Tuple[UUID, str, bytes]],
        tx: Optional[DBTransaction] = None,
    ) -> int:
        if not documents:
            return 0

        entities: List[DocumentChunk] = []
        batch_size = max(1, settings.vector.VECTOR_BATCH_SIZE)

        for document in documents:
            chunk_records = list(self._upload_document_processor.process([document]))

            if not chunk_records:
                self._logger.warning(f"No chunks found for the {document[0]}")
                continue

            self._logger.debug(
                f"Processing {len(chunk_records)} chunks for {document[0]}"
            )

            for start in range(0, len(chunk_records), batch_size):
                batch_records = chunk_records[start : start + batch_size]
                batch_texts = [chunk_text for _, chunk_text in batch_records]

                batch_vectors = list(self._embedder.embed_documents(batch_texts))
                if not batch_vectors:
                    self._logger.debug(f"No vectors found for {document[0]}")
                    continue

                vectors = batch_vectors[0]

                for (document_id, chunk_text), embedding in zip(batch_records, vectors):
                    entities.append(
                        DocumentChunk(
                            document_id=document_id,
                            chat_session_id=chat_session_id,
                            chunk_text=chunk_text,
                            embedding=embedding,
                        )
                    )
        self._logger.debug(
            f"Prepared {len(entities)} chunk entities for database upsert"
        )

        if not entities:
            return 0

        saved_chunks = await self._document_chunk_repository.upsert_many(entities, tx)

        self._logger.debug(f"{len(saved_chunks)} chunks uploaded")

        return len(saved_chunks)

    async def process_and_save_vectors_from_web(
        self,
        chat_session_id: UUID,
        raw_web_contents: List[str],
        tx: Optional[DBTransaction] = None,
    ) -> int:
        """
        Process a list of raw web content strings into chunks, embed them in
        batches and persist chunk records to the DocumentChunk repository.

        For web content we do not have a Document id, so `document_id` is left
        as None (the DB model allows that).
        """
        if not raw_web_contents:
            return 0

        entities: List[DocumentChunk] = []
        batch_size = max(1, settings.vector.VECTOR_BATCH_SIZE)

        for raw_content in raw_web_contents:
            # Ensure processor gets a list of contents (it yields chunk strings)
            chunk_texts = list(self._web_document_processor.process([raw_content]))

            if not chunk_texts:
                continue

            # embed in batches
            for start in range(0, len(chunk_texts), batch_size):
                batch_texts = chunk_texts[start : start + batch_size]

                # embed_documents is an iterator of batches; we call it on the batch list
                batch_vectors_iter = list(self._embedder.embed_documents(batch_texts))
                if not batch_vectors_iter:
                    continue

                vectors = batch_vectors_iter[0]

                for chunk_text, embedding in zip(batch_texts, vectors):
                    entities.append(
                        DocumentChunk(
                            document_id=None,
                            chat_session_id=chat_session_id,
                            chunk_text=chunk_text,
                            embedding=embedding,
                        )
                    )

        if not entities:
            return 0

        saved_chunks = await self._document_chunk_repository.upsert_many(entities, tx)
        return len(saved_chunks)
