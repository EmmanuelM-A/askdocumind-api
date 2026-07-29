from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional
from uuid import UUID
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import DocumentStream

from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from src.components.retrieval.embedder import Embedder
from src.database.models import DocumentChunk
from src.database.repository.interfaces import DBTransaction
from src.database.repository.interfaces.document_chunk_repository import (
    DocumentChunkRepositoryInterface,
)
from src.logger.base_logger import BaseLogger
from src.config.configs import settings


@dataclass
class ChunkingConfig:
    max_tokens: int


def get_chunking_config() -> ChunkingConfig:
    """Factory method to get the chunking configuration."""
    return ChunkingConfig(max_tokens=settings.vector.MAX_TOKENS)


def convert_to_docling_document(
    content: str, source_name: str, label: DocItemLabel
) -> DoclingDocument:
    doc = DoclingDocument(name=source_name)

    doc.add_text(label=label, text=content)

    return doc


class DocumentProcessor:
    """
    A class responsible for processing documents, including conversion,
    chunking, embedding, and saving to the database.
    """

    def __init__(
        self,
        converter: DocumentConverter,
        config: ChunkingConfig,
        embedder: Embedder,
        document_chunk_repository: DocumentChunkRepositoryInterface,
    ):
        self._converter = converter
        self._tokenizer = HuggingFaceTokenizer.from_pretrained(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            max_tokens=config.max_tokens,
        )
        self._chunker = HybridChunker(tokenizer=self._tokenizer, merge_peers=True)
        self._embedder = embedder
        self._document_chunk_repository = document_chunk_repository
        self._logger = BaseLogger(__name__)

    def extract(self, document_data: bytes, filename: str) -> DoclingDocument:
        stream = DocumentStream(name=filename, stream=BytesIO(document_data))

        result = self._converter.convert(stream)

        self._logger.debug(f"Extracted document: {result.document.name}")

        return result.document

    def chunk(self, docling_document: DoclingDocument, source_name: str) -> list[str]:
        """
        Chunk the document's content, prefixing each chunk with the
        document's source name so retrieval can also match on it (e.g. a
        query referencing the document/page name directly).
        """

        chunks_itr = self._chunker.chunk(docling_document)

        chunks = [
            f"Source: {source_name}\n\n{self._chunker.contextualize(chunk)}"
            for chunk in chunks_itr
        ]

        self._logger.debug(f"Chunked document into {len(chunks)} chunks")

        return chunks

    async def save_document_chunks(
        self,
        chunks: List[str],
        chat_session_id: UUID,
        document_id: UUID,
        tx: Optional[DBTransaction] = None,
    ) -> int:
        if len(chunks) == 0:
            self._logger.warning(f"No chunks to save for document_id: {document_id}")
            return 0

        entities: List[DocumentChunk] = []
        offset = 0

        for vector_batch in self._embedder.embed_documents(chunks):
            batch_chunk_texts = chunks[offset : offset + len(vector_batch)]
            offset += len(vector_batch)

            for chunk_text, embedding in zip(batch_chunk_texts, vector_batch):
                entities.append(
                    DocumentChunk(
                        document_id=document_id,
                        chat_session_id=chat_session_id,
                        chunk_text=chunk_text,
                        embedding=embedding,
                    )
                )

        if len(entities) == 0:
            self._logger.warning(
                f"No document chunks were created for document_id: {document_id}"
            )
            return 0

        self._logger.debug(
            f"Saving {len(entities)} document chunks for document_id: {document_id}"
        )

        saved_chunks = await self._document_chunk_repository.upsert_many(entities, tx)
        return len(saved_chunks)
