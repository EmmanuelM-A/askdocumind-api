from typing import List, Tuple
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
        self.upload_document_processor = upload_document_processor
        self.web_document_processor = web_document_processor
        self.embedder = embedder
        self.document_chunk_repository = document_chunk_repository
        self._logger = BaseLogger(__name__)

    async def process_and_save_vectors_from_uploads(
        self,
        chat_session_id: UUID,
        documents: List[Tuple[UUID, str, bytes]],
        tx: DBTransaction,
    ) -> int:
        if not documents:
            return 0

        entities: List[DocumentChunk] = []
        batch_size = max(1, settings.vector.VECTOR_BATCH_SIZE)

        for document in documents:
            chunk_records = list(self.upload_document_processor.process([document]))

            if not chunk_records:
                continue

            for start in range(0, len(chunk_records), batch_size):
                batch_records = chunk_records[start : start + batch_size]
                batch_texts = [chunk_text for _, chunk_text in batch_records]

                batch_vectors = list(self.embedder.embed_documents(batch_texts))
                if not batch_vectors:
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

        if not entities:
            return 0

        saved_chunks = await self.document_chunk_repository.upsert_many(entities, tx)

        return len(saved_chunks)

    def process_and_save_vectors_from_web(self):
        pass
