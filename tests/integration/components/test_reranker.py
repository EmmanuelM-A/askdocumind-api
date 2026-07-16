"""
Integration tests for the reranker module.

`CrossEncoderReranker.rerank` has no database dependency - it's a pure
in-memory scoring/sorting function over a list of `DocumentChunk` objects.
Per instruction, nothing is mocked here: a real `CrossEncoder` model
(`cross-encoder/ms-marco-MiniLM-L-6-v2`) is loaded and used to score real,
transient `DocumentChunk` instances (constructed in-memory, never persisted -
`rerank` never touches the database).

Most tests share a single module-scoped reranker instance so the model is
only loaded once; the couple of tests that specifically exercise lazy
loading construct their own fresh instance.
"""

from uuid import uuid4

import pytest

from src.components.retrieval.reranker import CrossEncoderReranker, Reranker
from src.database.models import DocumentChunk


# ==================== HELPERS ====================


def _chunk(text: str) -> DocumentChunk:
    """Builds a real, transient (never persisted) DocumentChunk."""
    return DocumentChunk(
        id=uuid4(),
        document_id=uuid4(),
        chat_session_id=uuid4(),
        chunk_text=text,
    )


# ==================== FIXTURES ====================


@pytest.fixture(scope="module")
def reranker():
    """A single real CrossEncoderReranker shared across most tests."""
    return CrossEncoderReranker()


# ==================== CORE FUNCTIONALITY ====================


@pytest.mark.asyncio
async def test_rerank_empty_chunks_returns_empty_list(reranker):
    """Test that reranking an empty chunk list returns an empty list."""
    result = await reranker.rerank("any query", [], top_k=5)

    assert result == []


@pytest.mark.asyncio
async def test_rerank_orders_by_relevance_to_query(reranker):
    """Test that the real cross-encoder ranks the more relevant chunk first."""
    relevant = _chunk("Python is a high-level, interpreted programming language.")
    irrelevant = _chunk("Bananas are a good source of potassium and fiber.")

    result = await reranker.rerank(
        "What is the Python programming language?", [irrelevant, relevant], top_k=2
    )

    assert result[0] is relevant
    assert result[1] is irrelevant


@pytest.mark.asyncio
async def test_rerank_respects_top_k_limit(reranker):
    """Test that only the top_k highest-scoring chunks are returned."""
    best = _chunk("The Eiffel Tower is located in Paris, France.")
    ok = _chunk("Paris is the capital city of France.")
    worst = _chunk("Cats often sleep for over twelve hours a day.")

    result = await reranker.rerank(
        "Where is the Eiffel Tower?", [worst, ok, best], top_k=2
    )

    assert len(result) == 2
    assert best in result
    assert worst not in result


@pytest.mark.asyncio
async def test_rerank_top_k_greater_than_chunk_count_returns_all(reranker):
    """Test that requesting more results than exist returns every chunk."""
    chunks = [_chunk("First chunk."), _chunk("Second chunk.")]

    result = await reranker.rerank("query", chunks, top_k=10)

    assert len(result) == 2
    assert set(result) == set(chunks)


@pytest.mark.asyncio
async def test_rerank_top_k_zero_returns_empty_list(reranker):
    """Test that top_k=0 returns no results even with candidate chunks."""
    chunks = [_chunk("Some content."), _chunk("More content.")]

    result = await reranker.rerank("query", chunks, top_k=0)

    assert result == []


@pytest.mark.asyncio
async def test_rerank_single_chunk_is_returned(reranker):
    """Test that a single-chunk input is returned regardless of relevance."""
    only_chunk = _chunk("Completely unrelated text about gardening.")

    result = await reranker.rerank("space travel", [only_chunk], top_k=5)

    assert result == [only_chunk]


@pytest.mark.asyncio
async def test_rerank_returns_original_chunk_objects(reranker):
    """Test that rerank returns the same DocumentChunk instances, not copies."""
    chunk_a = _chunk("Chunk A content about oceans.")
    chunk_b = _chunk("Chunk B content about mountains.")

    result = await reranker.rerank("oceans", [chunk_a, chunk_b], top_k=2)

    assert all(any(r is original for original in (chunk_a, chunk_b)) for r in result)


@pytest.mark.asyncio
async def test_rerank_does_not_mutate_input_list(reranker):
    """Test that the original input list's order is left untouched."""
    chunk_a = _chunk("Irrelevant text about shoes.")
    chunk_b = _chunk("The history of the Roman Empire.")
    original = [chunk_a, chunk_b]
    original_order = list(original)

    await reranker.rerank("Roman Empire history", original, top_k=2)

    assert original == original_order


@pytest.mark.asyncio
async def test_rerank_returns_a_list(reranker):
    """Test that the return type is a plain list."""
    result = await reranker.rerank("query", [_chunk("content")], top_k=1)

    assert isinstance(result, list)


# ==================== EDGE CASES ====================


@pytest.mark.asyncio
async def test_rerank_duplicate_content_chunks_keeps_stable_relative_order(reranker):
    """Test that chunks with identical text (equal scores) preserve their
    original relative order, since Python's sort is stable."""
    dup_1 = _chunk("Identical content for tie-breaking.")
    dup_2 = _chunk("Identical content for tie-breaking.")

    result = await reranker.rerank("tie-breaking", [dup_1, dup_2], top_k=2)

    assert result == [dup_1, dup_2]


@pytest.mark.asyncio
async def test_rerank_negative_top_k_drops_lowest_scoring_chunk(reranker):
    """Test the actual (unvalidated) behavior of a negative top_k: Python
    slicing with a negative index drops that many lowest-ranked results
    rather than raising, since rerank() does not validate top_k."""
    best = _chunk("The capital of Japan is Tokyo.")
    worst = _chunk("Sandwiches are commonly eaten for lunch.")

    result = await reranker.rerank("capital of Japan", [worst, best], top_k=-1)

    assert result == [best]


@pytest.mark.asyncio
async def test_rerank_many_chunks_all_scored_and_sorted(reranker):
    """Test reranking a larger batch of chunks still produces a fully sorted result."""
    chunks = [_chunk(f"Document chunk number {i} about topic {i}.") for i in range(10)]
    target = _chunk("The mitochondria is the powerhouse of the cell.")
    chunks.append(target)

    result = await reranker.rerank("What is the powerhouse of the cell?", chunks, top_k=3)

    assert len(result) == 3
    assert result[0] is target


# ==================== LAZY MODEL LOADING ====================


@pytest.mark.asyncio
async def test_reranker_model_not_loaded_before_first_call():
    """Test that the CrossEncoder model is not loaded until rerank() is first called."""
    fresh_reranker = CrossEncoderReranker()

    assert fresh_reranker.reranker is None


@pytest.mark.asyncio
async def test_reranker_loads_model_lazily_on_first_call():
    """Test that the model is loaded exactly when rerank() is first invoked."""
    fresh_reranker = CrossEncoderReranker()

    await fresh_reranker.rerank("query", [_chunk("content")], top_k=1)

    assert fresh_reranker.reranker is not None


@pytest.mark.asyncio
async def test_reranker_reuses_loaded_model_across_calls():
    """Test that a second rerank() call does not reload the model."""
    fresh_reranker = CrossEncoderReranker()

    await fresh_reranker.rerank("first query", [_chunk("content one")], top_k=1)
    loaded_model = fresh_reranker.reranker

    await fresh_reranker.rerank("second query", [_chunk("content two")], top_k=1)

    assert fresh_reranker.reranker is loaded_model


# ==================== ABSTRACT BASE CLASS ====================


def test_reranker_abstract_base_class_cannot_be_instantiated():
    """Test that the Reranker ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        Reranker() # type: ignore
