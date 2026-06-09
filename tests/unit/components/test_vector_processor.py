"""
Unit tests for the VectorProcessor component.
Tests document processing, embedding, and vector storage functionality.
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.components.ingestion.vector_processor import VectorProcessor
from src.database.models import DocumentChunk


# ==================== FIXTURES ====================


@pytest.fixture
def mock_upload_document_processor():
    """Creates a mock UploadedDocumentProcessor instance."""
    mock_proc = Mock()
    mock_proc.process.return_value = iter([])
    return mock_proc


@pytest.fixture
def mock_web_document_processor():
    """Creates a mock WebDocumentProcessor instance."""
    mock_proc = Mock()
    mock_proc.process.return_value = iter([])
    return mock_proc


@pytest.fixture
def mock_document_chunk_repository():
    """Creates a mock DocumentChunkRepository instance."""
    mock_repo = Mock()
    mock_repo.upsert_many = AsyncMock(return_value=[])
    return mock_repo


@pytest.fixture
def vector_processor(mock_embedder, mock_upload_document_processor, 
                    mock_web_document_processor, mock_document_chunk_repository):
    """Provides a VectorProcessor instance with mocked dependencies."""
    return VectorProcessor(
        upload_document_processor=mock_upload_document_processor,
        web_document_processor=mock_web_document_processor,
        embedder=mock_embedder,
        document_chunk_repository=mock_document_chunk_repository,
    )


# ==================== INITIALIZATION TESTS ====================


def test_vector_processor_initialization(mock_embedder, mock_upload_document_processor,
                                       mock_web_document_processor, mock_document_chunk_repository):
    """Test successful VectorProcessor initialization with mocked dependencies."""
    processor = VectorProcessor(
        upload_document_processor=mock_upload_document_processor,
        web_document_processor=mock_web_document_processor,
        embedder=mock_embedder,
        document_chunk_repository=mock_document_chunk_repository,
    )

    assert processor._upload_document_processor is mock_upload_document_processor
    assert processor._web_document_processor is mock_web_document_processor
    assert processor._embedder is mock_embedder
    assert processor._document_chunk_repository is mock_document_chunk_repository


# ==================== PROCESS AND SAVE VECTORS FROM UPLOADS TESTS ====================


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_uploads_success(vector_processor):
    """Test successfully processing and saving vectors from uploaded documents."""
    chat_session_id = uuid4()
    document_id = uuid4()
    tx = Mock()

    # Create sample document
    documents = [(document_id, "test.txt", b"Some test content")]

    # Mock upload processor to return chunks
    chunk_records = [
        (document_id, "Chunk 1 text"),
        (document_id, "Chunk 2 text"),
    ]
    vector_processor._upload_document_processor.process.return_value = iter(chunk_records)

    # Mock embedder to return embeddings
    mock_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    vector_processor._embedder.embed_documents.return_value = iter([mock_embeddings])

    # Mock repository to return saved chunks
    saved_chunks = [
        DocumentChunk(
            document_id=document_id,
            chat_session_id=chat_session_id,
            chunk_text="Chunk 1 text",
            embedding=[0.1, 0.2, 0.3],
        ),
        DocumentChunk(
            document_id=document_id,
            chat_session_id=chat_session_id,
            chunk_text="Chunk 2 text",
            embedding=[0.4, 0.5, 0.6],
        ),
    ]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    result = await vector_processor.process_and_save_vectors_from_uploads(
        chat_session_id, documents, tx
    )

    assert result == 2
    vector_processor._upload_document_processor.process.assert_called_once_with(documents)
    vector_processor._embedder.embed_documents.assert_called_once()
    vector_processor._document_chunk_repository.upsert_many.assert_called_once()


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_uploads_empty_documents(vector_processor):
    """Test processing returns 0 when no documents provided."""
    chat_session_id = uuid4()
    tx = Mock()

    result = await vector_processor.process_and_save_vectors_from_uploads(
        chat_session_id, [], tx
    )

    assert result == 0
    vector_processor._upload_document_processor.process.assert_not_called()
    vector_processor._document_chunk_repository.upsert_many.assert_not_called()


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_uploads_no_chunks(vector_processor):
    """Test processing returns 0 when documents yield no chunks."""
    chat_session_id = uuid4()
    document_id = uuid4()
    tx = Mock()

    documents = [(document_id, "empty.txt", b"")]
    vector_processor._upload_document_processor.process.return_value = iter([])

    result = await vector_processor.process_and_save_vectors_from_uploads(
        chat_session_id, documents, tx
    )

    assert result == 0
    vector_processor._document_chunk_repository.upsert_many.assert_not_called()


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_uploads_batching(vector_processor):
    """Test that vectors are processed in batches according to VECTOR_BATCH_SIZE."""
    chat_session_id = uuid4()
    document_id = uuid4()
    tx = Mock()

    documents = [(document_id, "test.txt", b"content")]

    # Create 5 chunks (will be batched based on settings)
    chunk_records = [
        (document_id, f"Chunk {i} text") for i in range(1, 6)
    ]
    vector_processor._upload_document_processor.process.return_value = iter(chunk_records)

    # Mock embedder to return batches of embeddings
    batch1_embeddings = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]  # 3 embeddings
    batch2_embeddings = [[0.7, 0.8], [0.9, 1.0]]  # 2 embeddings
    vector_processor._embedder.embed_documents.side_effect = [
        iter([batch1_embeddings]),
        iter([batch2_embeddings]),
    ]

    saved_chunks = [Mock() for _ in range(5)]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    with patch("src.components.ingestion.vector_processor.settings") as mock_settings:
        mock_settings.vector.VECTOR_BATCH_SIZE = 3

        result = await vector_processor.process_and_save_vectors_from_uploads(
            chat_session_id, documents, tx
        )

    assert result == 5
    # Should have called embedder twice (one for each batch)
    assert vector_processor._embedder.embed_documents.call_count == 2


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_uploads_multiple_documents(vector_processor):
    """Test processing multiple documents."""
    chat_session_id = uuid4()
    doc1_id = uuid4()
    doc2_id = uuid4()
    tx = Mock()

    documents = [
        (doc1_id, "doc1.txt", b"content1"),
        (doc2_id, "doc2.txt", b"content2"),
    ]

    # Mock chunks from both documents
    chunk_records = [
        (doc1_id, "Doc1 Chunk 1"),
        (doc1_id, "Doc1 Chunk 2"),
        (doc2_id, "Doc2 Chunk 1"),
    ]
    vector_processor._upload_document_processor.process.return_value = iter(chunk_records)

    mock_embeddings = [
        [0.1, 0.2],
        [0.3, 0.4],
        [0.5, 0.6],
    ]
    vector_processor._embedder.embed_documents.return_value = iter([mock_embeddings])

    saved_chunks = [Mock() for _ in range(3)]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    result = await vector_processor.process_and_save_vectors_from_uploads(
        chat_session_id, documents, tx
    )

    assert result == 3


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_uploads_no_embeddings(vector_processor):
    """Test handling when embedder returns no embeddings for a batch."""
    chat_session_id = uuid4()
    document_id = uuid4()
    tx = Mock()

    documents = [(document_id, "test.txt", b"content")]

    chunk_records = [
        (document_id, "Chunk 1"),
        (document_id, "Chunk 2"),
    ]
    vector_processor._upload_document_processor.process.return_value = iter(chunk_records)

    # Embedder returns empty batch
    vector_processor._embedder.embed_documents.return_value = iter([])

    result = await vector_processor.process_and_save_vectors_from_uploads(
        chat_session_id, documents, tx
    )

    assert result == 0
    vector_processor._document_chunk_repository.upsert_many.assert_not_called()


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_uploads_passes_transaction(vector_processor):
    """Test that transaction is passed to repository."""
    chat_session_id = uuid4()
    document_id = uuid4()
    tx = Mock()

    documents = [(document_id, "test.txt", b"content")]

    chunk_records = [(document_id, "Chunk 1")]
    vector_processor._upload_document_processor.process.return_value = iter(chunk_records)

    vector_processor._embedder.embed_documents.return_value = iter([[[0.1, 0.2]]])

    saved_chunks = [Mock()]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    await vector_processor.process_and_save_vectors_from_uploads(
        chat_session_id, documents, tx
    )

    # Verify transaction was passed to upsert_many
    call_args = vector_processor._document_chunk_repository.upsert_many.call_args
    assert call_args[0][1] is tx  # Second positional argument should be tx


# ==================== PROCESS AND SAVE VECTORS FROM WEB TESTS ====================


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_web_success(vector_processor):
    """Test successfully processing and saving vectors from web content."""
    chat_session_id = uuid4()
    tx = Mock()

    web_contents = ["Web content 1", "Web content 2"]

    # Mock web processor to return chunks - called once per web_content
    chunk_texts_batch1 = ["Web chunk 1"]
    chunk_texts_batch2 = ["Web chunk 2", "Web chunk 3"]
    vector_processor._web_document_processor.process.side_effect = [
        iter(chunk_texts_batch1),
        iter(chunk_texts_batch2),
    ]

    # Mock embedder to return embeddings
    mock_embeddings_batch1 = [[0.1, 0.2, 0.3]]
    mock_embeddings_batch2 = [[0.4, 0.5, 0.6], [0.7, 0.8, 0.9]]
    vector_processor._embedder.embed_documents.side_effect = [
        iter([mock_embeddings_batch1]),
        iter([mock_embeddings_batch2]),
    ]

    # Mock repository to return saved chunks
    saved_chunks = [Mock() for _ in range(3)]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    result = await vector_processor.process_and_save_vectors_from_web(
        chat_session_id, web_contents, tx
    )

    assert result == 3
    # Process is called once per web_content
    assert vector_processor._web_document_processor.process.call_count == 2
    # embedder is called once per web_content
    assert vector_processor._embedder.embed_documents.call_count == 2
    vector_processor._document_chunk_repository.upsert_many.assert_called_once()


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_web_empty_contents(vector_processor):
    """Test processing returns 0 when no web contents provided."""
    chat_session_id = uuid4()
    tx = Mock()

    result = await vector_processor.process_and_save_vectors_from_web(
        chat_session_id, [], tx
    )

    assert result == 0
    vector_processor._web_document_processor.process.assert_not_called()
    vector_processor._document_chunk_repository.upsert_many.assert_not_called()


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_web_no_chunks(vector_processor):
    """Test processing returns 0 when web content yields no chunks."""
    chat_session_id = uuid4()
    tx = Mock()

    web_contents = ["Empty content"]
    vector_processor._web_document_processor.process.return_value = iter([])

    result = await vector_processor.process_and_save_vectors_from_web(
        chat_session_id, web_contents, tx
    )

    assert result == 0
    vector_processor._document_chunk_repository.upsert_many.assert_not_called()


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_web_document_id_is_none(vector_processor):
    """Test that web content chunks have document_id set to None."""
    chat_session_id = uuid4()
    tx = Mock()

    web_contents = ["Web content"]

    chunk_texts = ["Web chunk 1", "Web chunk 2"]
    vector_processor._web_document_processor.process.return_value = iter(chunk_texts)

    mock_embeddings = [[0.1, 0.2], [0.3, 0.4]]
    vector_processor._embedder.embed_documents.return_value = iter([mock_embeddings])

    saved_chunks = [Mock() for _ in range(2)]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    await vector_processor.process_and_save_vectors_from_web(
        chat_session_id, web_contents, tx
    )

    # Check that entities passed to upsert_many have document_id=None
    call_args = vector_processor._document_chunk_repository.upsert_many.call_args
    entities = call_args[0][0]
    assert all(chunk.document_id is None for chunk in entities)


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_web_batching(vector_processor):
    """Test that web content vectors are processed in batches."""
    chat_session_id = uuid4()
    tx = Mock()

    web_contents = ["Web content"]

    # Create 5 chunks
    chunk_texts = [f"Web chunk {i}" for i in range(1, 6)]
    vector_processor._web_document_processor.process.return_value = iter(chunk_texts)

    # Mock embedder to return batches
    batch1_embeddings = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
    batch2_embeddings = [[0.7, 0.8], [0.9, 1.0]]
    vector_processor._embedder.embed_documents.side_effect = [
        iter([batch1_embeddings]),
        iter([batch2_embeddings]),
    ]

    saved_chunks = [Mock() for _ in range(5)]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    with patch("src.components.ingestion.vector_processor.settings") as mock_settings:
        mock_settings.vector.VECTOR_BATCH_SIZE = 3

        result = await vector_processor.process_and_save_vectors_from_web(
            chat_session_id, web_contents, tx
        )

    assert result == 5
    # Should have called embedder twice for batching
    assert vector_processor._embedder.embed_documents.call_count == 2


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_web_multiple_contents(vector_processor):
    """Test processing multiple web contents."""
    chat_session_id = uuid4()
    tx = Mock()

    web_contents = ["Content 1", "Content 2"]

    # Processor is called once per web_content, returns chunks each time
    chunk_texts_batch1 = ["Chunk 1", "Chunk 2"]
    chunk_texts_batch2 = ["Chunk 3"]
    vector_processor._web_document_processor.process.side_effect = [
        iter(chunk_texts_batch1),
        iter(chunk_texts_batch2),
    ]

    # Embedder is called once per web_content
    mock_embeddings_batch1 = [[0.1, 0.2], [0.3, 0.4]]
    mock_embeddings_batch2 = [[0.5, 0.6]]
    vector_processor._embedder.embed_documents.side_effect = [
        iter([mock_embeddings_batch1]),
        iter([mock_embeddings_batch2]),
    ]

    saved_chunks = [Mock() for _ in range(3)]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    result = await vector_processor.process_and_save_vectors_from_web(
        chat_session_id, web_contents, tx
    )

    assert result == 3
    # Process should be called once per web_content
    assert vector_processor._web_document_processor.process.call_count == 2
    # Verify it was called with each content individually
    calls = vector_processor._web_document_processor.process.call_args_list
    assert calls[0][0][0] == ["Content 1"]
    assert calls[1][0][0] == ["Content 2"]


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_web_no_embeddings(vector_processor):
    """Test handling when embedder returns no embeddings for a batch."""
    chat_session_id = uuid4()
    tx = Mock()

    web_contents = ["Web content"]

    chunk_texts = ["Chunk 1", "Chunk 2"]
    vector_processor._web_document_processor.process.return_value = iter(chunk_texts)

    # Embedder returns empty batch
    vector_processor._embedder.embed_documents.return_value = iter([])

    result = await vector_processor.process_and_save_vectors_from_web(
        chat_session_id, web_contents, tx
    )

    assert result == 0
    vector_processor._document_chunk_repository.upsert_many.assert_not_called()


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_web_passes_transaction(vector_processor):
    """Test that transaction is passed to repository for web content."""
    chat_session_id = uuid4()
    tx = Mock()

    web_contents = ["Web content"]

    chunk_texts = ["Chunk 1"]
    vector_processor._web_document_processor.process.return_value = iter(chunk_texts)

    vector_processor._embedder.embed_documents.return_value = iter([[[0.1, 0.2]]])

    saved_chunks = [Mock()]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    await vector_processor.process_and_save_vectors_from_web(
        chat_session_id, web_contents, tx
    )

    # Verify transaction was passed to upsert_many
    call_args = vector_processor._document_chunk_repository.upsert_many.call_args
    assert call_args[0][1] is tx  # Second positional argument should be tx


# ==================== DOCUMENT CHUNK ENTITY CREATION TESTS ====================


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_uploads_creates_correct_entities(vector_processor):
    """Test that correct DocumentChunk entities are created with all fields."""
    chat_session_id = uuid4()
    document_id = uuid4()
    tx = Mock()

    documents = [(document_id, "test.txt", b"content")]

    chunk_records = [
        (document_id, "Test chunk text"),
    ]
    vector_processor._upload_document_processor.process.return_value = iter(chunk_records)

    test_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    vector_processor._embedder.embed_documents.return_value = iter([[test_embedding]])

    saved_chunks = [Mock()]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    await vector_processor.process_and_save_vectors_from_uploads(
        chat_session_id, documents, tx
    )

    call_args = vector_processor._document_chunk_repository.upsert_many.call_args
    entities = call_args[0][0]

    assert len(entities) == 1
    entity = entities[0]
    assert entity.document_id == document_id
    assert entity.chat_session_id == chat_session_id
    assert entity.chunk_text == "Test chunk text"
    assert entity.embedding == test_embedding


@pytest.mark.asyncio
async def test_process_and_save_vectors_from_web_creates_correct_entities(vector_processor):
    """Test that correct DocumentChunk entities are created for web content."""
    chat_session_id = uuid4()
    tx = Mock()

    web_contents = ["Web source"]

    chunk_texts = ["Web chunk text"]
    vector_processor._web_document_processor.process.return_value = iter(chunk_texts)

    test_embedding = [0.5, 0.6, 0.7]
    vector_processor._embedder.embed_documents.return_value = iter([[test_embedding]])

    saved_chunks = [Mock()]
    vector_processor._document_chunk_repository.upsert_many.return_value = saved_chunks

    await vector_processor.process_and_save_vectors_from_web(
        chat_session_id, web_contents, tx
    )

    call_args = vector_processor._document_chunk_repository.upsert_many.call_args
    entities = call_args[0][0]

    assert len(entities) == 1
    entity = entities[0]
    assert entity.document_id is None  # Web content has no document_id
    assert entity.chat_session_id == chat_session_id
    assert entity.chunk_text == "Web chunk text"
    assert entity.embedding == test_embedding



