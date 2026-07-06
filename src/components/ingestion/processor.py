from dataclasses import dataclass
from io import BytesIO
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import DocumentStream
from docling_core.types.doc.document import DoclingDocument

from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from transformers import AutoTokenizer


@dataclass
class ChunkingConfig:
    max_tokens: int


class DocumentProcessor:

    def __init__(self, converter: DocumentConverter, config: ChunkingConfig):
        self._converter = converter

        # Initialize tokenizer for token-aware chunking
        self._tokenizer = AutoTokenizer.from_pretrained(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

        self._chunker = HybridChunker(
            tokenizer=self._tokenizer, max_tokens=config.max_tokens, merge_peers=True
        )

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
