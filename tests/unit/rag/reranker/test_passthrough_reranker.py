"""
Unit tests for PassthroughReranker, used when RERANKER_ENABLED is false.
"""

from types import SimpleNamespace

import pytest

from src.rag.services.rerank.passthrough_reranker import PassthroughReranker

pytestmark = pytest.mark.asyncio


async def test_keeps_the_retrieval_order():
    chunks = [SimpleNamespace(chunk_text=text) for text in ("c", "a", "b")]

    result = await PassthroughReranker().rerank("query", chunks)

    assert result == chunks


async def test_returns_a_new_list():
    chunks = [SimpleNamespace(chunk_text="a")]

    result = await PassthroughReranker().rerank("query", chunks)

    assert result is not chunks


async def test_empty_input_returns_empty_list():
    assert await PassthroughReranker().rerank("query", []) == []
