"""
Unit tests for the DocumentProcessor class.

Tests cover:
- Initialization / dependency wiring
- Document extraction (conversion via DocumentConverter)
- Chunking orchestration
- Building a DoclingDocument from raw text
- Embedding + persisting document chunks

The DocumentConverter, HuggingFaceTokenizer and HybridChunker are backed by
heavy third-party ML models (network downloads / GPU-capable libraries), so
they are mocked - their own correctness is docling's responsibility, not
DocumentProcessor's. The Embedder is likewise mocked here since its internal
batching behaviour already has dedicated coverage in test_embedder.py; what
we care about in this file is DocumentProcessor's own orchestration logic
(how it turns embedding batches into DocumentChunk entities).
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from src.components.ingestion.document_processor import (
    ChunkingConfig,
    DocumentProcessor,
    convert_to_docling_document,
    get_chunking_config,
)


# ==================== FIXTURES ====================


@pytest.fixture
def mock_converter():
    return Mock()


@pytest.fixture
def mock_embedder():
    return Mock()


@pytest.fixture
def mock_repository():
    repo = Mock()
    repo.upsert_many = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def document_processor(mock_converter, mock_embedder, mock_repository):
    """DocumentProcessor with a stubbed-out tokenizer/chunker (avoids a real
    HuggingFace model download) but real, injected business-logic objects."""
    with patch(
        "src.components.ingestion.document_processor.HuggingFaceTokenizer"
    ) as mock_tokenizer_cls, patch(
        "src.components.ingestion.document_processor.HybridChunker"
    ) as mock_chunker_cls:
        mock_tokenizer_cls.from_pretrained.return_value = Mock()
        mock_chunker_cls.return_value = Mock()

        processor = DocumentProcessor(
            converter=mock_converter,
            config=ChunkingConfig(max_tokens=512),
            embedder=mock_embedder,
            document_chunk_repository=mock_repository,
        )
        yield processor


# ==================== INITIALIZATION ====================


def test_init_creates_tokenizer_and_chunker_with_correct_config(
    mock_converter, mock_embedder, mock_repository
):
    """Test that the tokenizer/chunker are constructed using the chunking config."""
    with patch(
        "src.components.ingestion.document_processor.HuggingFaceTokenizer"
    ) as mock_tokenizer_cls, patch(
        "src.components.ingestion.document_processor.HybridChunker"
    ) as mock_chunker_cls:
        mock_tokenizer = Mock()
        mock_tokenizer_cls.from_pretrained.return_value = mock_tokenizer

        DocumentProcessor(
            converter=mock_converter,
            config=ChunkingConfig(max_tokens=256),
            embedder=mock_embedder,
            document_chunk_repository=mock_repository,
        )

        mock_tokenizer_cls.from_pretrained.assert_called_once_with(
            model_name="sentence-transformers/all-MiniLM-L6-v2", max_tokens=256
        )
        mock_chunker_cls.assert_called_once_with(
            tokenizer=mock_tokenizer, merge_peers=True
        )


def test_init_stores_dependencies(document_processor, mock_converter, mock_embedder, mock_repository):
    """Test that constructor arguments are stored for later use."""
    assert document_processor._converter is mock_converter
    assert document_processor._embedder is mock_embedder
    assert document_processor._document_chunk_repository is mock_repository


# ==================== EXTRACT ====================


def test_extract_returns_converted_document(document_processor, mock_converter):
    """Test that extract() returns the docling document from the converter's result."""
    mock_document = Mock()
    mock_document.name = "result.pdf"
    mock_converter.convert.return_value = Mock(document=mock_document)

    result = document_processor.extract(b"raw bytes", "result.pdf")

    assert result is mock_document


def test_extract_builds_document_stream_with_correct_name(document_processor, mock_converter):
    """Test that extract() passes a DocumentStream with the given filename to the converter."""
    mock_converter.convert.return_value = Mock(document=Mock(name="doc.txt"))

    document_processor.extract(b"content", "doc.txt")

    stream_arg = mock_converter.convert.call_args[0][0]
    assert stream_arg.name == "doc.txt"
    assert stream_arg.stream.read() == b"content"


def test_extract_propagates_converter_errors(document_processor, mock_converter):
    """Test that extract() does not swallow converter failures."""
    mock_converter.convert.side_effect = RuntimeError("conversion failed")

    with pytest.raises(RuntimeError, match="conversion failed"):
        document_processor.extract(b"content", "bad.pdf")


# ==================== CHUNK ====================


def test_chunk_returns_contextualized_chunks_in_order(document_processor):
    """Test that chunk() contextualizes every chunk yielded by the chunker,
    in order, and prefixes each with the source name."""
    raw_chunk_1, raw_chunk_2 = Mock(), Mock()
    document_processor._chunker.chunk.return_value = iter([raw_chunk_1, raw_chunk_2])
    document_processor._chunker.contextualize.side_effect = ["text-1", "text-2"]

    result = document_processor.chunk(Mock(spec=DoclingDocument), source_name="doc.pdf")

    assert result == [
        "Source: doc.pdf\n\ntext-1",
        "Source: doc.pdf\n\ntext-2",
    ]
    document_processor._chunker.contextualize.assert_any_call(raw_chunk_1)
    document_processor._chunker.contextualize.assert_any_call(raw_chunk_2)


def test_chunk_empty_document_returns_empty_list(document_processor):
    """Test that chunk() returns an empty list when the chunker yields no chunks."""
    document_processor._chunker.chunk.return_value = iter([])

    result = document_processor.chunk(Mock(spec=DoclingDocument), source_name="doc.pdf")

    assert result == []
    document_processor._chunker.contextualize.assert_not_called()


# ==================== CONVERT TO DOCLING DOCUMENT ====================


def test_convert_to_docling_document_creates_document_with_text():
    """Test that a real DoclingDocument is built containing the given text."""
    doc = convert_to_docling_document("Hello world", "source.txt", DocItemLabel.PARAGRAPH)

    assert isinstance(doc, DoclingDocument)
    assert doc.name == "source.txt"
    assert doc.texts[0].text == "Hello world"


def test_convert_to_docling_document_uses_given_label():
    """Test that the text item is tagged with the provided DocItemLabel."""
    doc = convert_to_docling_document("A title", "source.txt", DocItemLabel.TITLE)

    assert doc.texts[0].label == DocItemLabel.TITLE


# ==================== SAVE DOCUMENT CHUNKS ====================


@pytest.mark.asyncio
async def test_save_document_chunks_empty_list_returns_zero(document_processor, mock_repository):
    """Test that saving an empty chunk list is a no-op."""
    result = await document_processor.save_document_chunks([], uuid4(), uuid4())

    assert result == 0
    mock_repository.upsert_many.assert_not_called()


@pytest.mark.asyncio
async def test_save_document_chunks_single_batch_success(
    document_processor, mock_embedder, mock_repository
):
    """Test the happy path: chunks embedded in one batch are saved and counted."""
    chat_session_id = uuid4()
    document_id = uuid4()
    chunks = ["chunk one", "chunk two"]
    mock_embedder.embed_documents.return_value = iter([[[0.1, 0.2], [0.3, 0.4]]])
    mock_repository.upsert_many.return_value = [uuid4(), uuid4()]

    result = await document_processor.save_document_chunks(
        chunks, chat_session_id, document_id
    )

    assert result == 2
    saved_entities = mock_repository.upsert_many.call_args[0][0]
    assert [e.chunk_text for e in saved_entities] == chunks
    assert [e.embedding for e in saved_entities] == [[0.1, 0.2], [0.3, 0.4]]
    assert all(e.document_id == document_id for e in saved_entities)
    assert all(e.chat_session_id == chat_session_id for e in saved_entities)


@pytest.mark.asyncio
async def test_save_document_chunks_multiple_batches_align_text_and_embeddings(
    document_processor, mock_embedder, mock_repository
):
    """Test that chunk text stays correctly aligned with embeddings across batches."""
    chunks = ["c1", "c2", "c3"]
    mock_embedder.embed_documents.return_value = iter(
        [[[0.1], [0.2]], [[0.3]]]
    )
    mock_repository.upsert_many.return_value = [uuid4(), uuid4(), uuid4()]

    await document_processor.save_document_chunks(chunks, uuid4(), uuid4())

    saved_entities = mock_repository.upsert_many.call_args[0][0]
    assert [e.chunk_text for e in saved_entities] == ["c1", "c2", "c3"]
    assert [e.embedding for e in saved_entities] == [[0.1], [0.2], [0.3]]


@pytest.mark.asyncio
async def test_save_document_chunks_no_embeddings_returns_zero(
    document_processor, mock_embedder, mock_repository
):
    """Test that no entities are saved when the embedder yields no batches."""
    mock_embedder.embed_documents.return_value = iter([])

    result = await document_processor.save_document_chunks(["chunk"], uuid4(), uuid4())

    assert result == 0
    mock_repository.upsert_many.assert_not_called()


@pytest.mark.asyncio
async def test_save_document_chunks_passes_transaction_through(
    document_processor, mock_embedder, mock_repository
):
    """Test that an optional transaction is forwarded to the repository call."""
    tx = Mock()
    mock_embedder.embed_documents.return_value = iter([[[0.1]]])
    mock_repository.upsert_many.return_value = [uuid4()]

    await document_processor.save_document_chunks(["chunk"], uuid4(), uuid4(), tx=tx)

    assert mock_repository.upsert_many.call_args[0][1] is tx


@pytest.mark.asyncio
async def test_save_document_chunks_returns_repository_saved_count(
    document_processor, mock_embedder, mock_repository
):
    """Test that the return value reflects what the repository reports as saved,
    not simply the number of entities that were built."""
    mock_embedder.embed_documents.return_value = iter([[[0.1], [0.2]]])
    mock_repository.upsert_many.return_value = [uuid4()]

    result = await document_processor.save_document_chunks(
        ["chunk-a", "chunk-b"], uuid4(), uuid4()
    )

    assert result == 1


# ==================== GET CHUNKING CONFIG ====================


def test_get_chunking_config_uses_settings():
    """Test that the factory reads MAX_TOKENS from application settings."""
    with patch("src.components.ingestion.document_processor.settings") as mock_settings:
        mock_settings.vector.MAX_TOKENS = 999

        config = get_chunking_config()

    assert config == ChunkingConfig(max_tokens=999)
