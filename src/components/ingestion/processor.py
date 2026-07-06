from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional
from uuid import UUID
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import DocumentStream
from docling_core.types.doc.document import DoclingDocument

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


@dataclass
class ChunkingConfig:
    max_tokens: int


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
        self._chunker = HybridChunker(
            tokenizer=self._tokenizer, merge_peers=True
        )
        self._embedder = embedder
        self._document_chunk_repository = document_chunk_repository

    def extract(self, document_data: bytes, filename: str) -> DoclingDocument:
        stream = DocumentStream(name=filename, stream=BytesIO(document_data))
        result = self._converter.convert(stream)
        return result.document

    def chunk(self, docling_document: DoclingDocument) -> list[str]:
        chunks = self._chunker.chunk(docling_document)
        return [self._chunker.contextualize(chunk) for chunk in chunks]

    def convert_to_docling_document(
        self, content: str, filename: str
    ) -> DoclingDocument:
        doc = DoclingDocument(name=filename)
        doc.add_text(label=DocItemLabel.TEXT, text=content)
        return doc

    async def save_document_chunks(
        self,
        chunks: List[str],
        chat_session_id: UUID,
        document_id: UUID,
        tx: Optional[DBTransaction] = None,
    ) -> int:
        if len(chunks) == 0:
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
            return 0

        saved_chunks = await self._document_chunk_repository.upsert_many(entities, tx)
        return len(saved_chunks)
