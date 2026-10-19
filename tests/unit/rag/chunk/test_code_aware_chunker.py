"""
Unit tests for CodeAwareChunker.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.rag.services.chunk.chunker import Chunk, Chunker
from src.rag.services.chunk.code_aware import (
    CodeAwareChunker,
    CodeAwareChunkerConfig,
)
from src.rag.services.extract.extractors.extractor import Segment

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_logger():
    """
    Replace the module-level logger with a plain mock so tests do not depend
    on the real logging setup, and so warning/exception calls can be
    asserted on.
    """
    with patch("src.rag.services.chunk.code_aware._logger") as mock_logger:
        yield mock_logger


@pytest.fixture
def source_id():
    return uuid4()


@pytest.fixture
def fallback_chunker():
    """A stub Chunker whose chunk() result each test sets directly."""
    stub = AsyncMock(spec=Chunker)
    stub.chunk.return_value = []
    return stub


def make_chunker(**overrides) -> CodeAwareChunker:
    config = CodeAwareChunkerConfig(**overrides)
    return CodeAwareChunker(config)


# Sample source snippets used across tests
SIMPLE_SOURCE = """\
def add(a, b):
    return a + b


def subtract(a, b):
    return a - b
"""

SOURCE_WITH_PREAMBLE = '''\
"""Module docstring."""
import os

def add(a, b):
    return a + b
'''

SOURCE_WITH_CLASS = """\
class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
"""

UNICODE_SOURCE = """\
def greet():
    return "héllo wörld 你好"


def farewell():
    return "adiós"
"""

# Source that parses to essentially nothing but ERROR nodes for any grammar,
# used to test the parse-failure and error-threshold fallback paths.
BROKEN_SOURCE = ")))  &&&  {{{ not valid syntax at all !!!  ###"

LONG_FUNCTION_SOURCE = (
    "def big():\n" + "\n".join(f"    x{i} = {i}" for i in range(20)) + "\n"
)

LONG_FUNCTION_WITH_NESTED = (
    "def outer():\n"
    "    def inner_one():\n"
    "        pass\n\n"
    "    def inner_two():\n"
    "        pass\n" + "\n".join(f"    y{i} = {i}" for i in range(20)) + "\n"
)


# ---------------------------------------------------------------------------
# Core functionality
# ---------------------------------------------------------------------------


class TestCoreChunking:

    @pytest.mark.asyncio
    async def test_splits_top_level_functions_into_separate_chunks(self, source_id):
        chunker = make_chunker()
        chunks = await chunker.chunk(SIMPLE_SOURCE, source_id)

        assert len(chunks) == 2
        assert "def add" in chunks[0].text
        assert "def subtract" in chunks[1].text

    @pytest.mark.asyncio
    async def test_chunk_metadata_includes_node_type_and_language(self, source_id):
        chunker = make_chunker(language="python")
        chunks = await chunker.chunk(SIMPLE_SOURCE, source_id)

        for c in chunks:
            assert c.metadata["node_type"] == "function_definition"
            assert c.metadata["language"] == "python"

    @pytest.mark.asyncio
    async def test_preamble_before_first_function_is_its_own_chunk(self, source_id):
        chunker = make_chunker()
        chunks = await chunker.chunk(SOURCE_WITH_PREAMBLE, source_id)

        assert chunks[0].metadata["node_type"] == "preamble"
        assert "docstring" in chunks[0].text
        assert chunks[1].metadata["node_type"] == "function_definition"

    @pytest.mark.asyncio
    async def test_class_is_kept_as_single_chunk_by_default(self, source_id):
        # split_node_types matches class_definition first and does not
        # descend into its methods once a match is found.
        chunker = make_chunker()
        chunks = await chunker.chunk(SOURCE_WITH_CLASS, source_id)

        assert len(chunks) == 1
        assert chunks[0].metadata["node_type"] == "class_definition"
        assert "def add" in chunks[0].text
        assert "def subtract" in chunks[0].text

    @pytest.mark.asyncio
    async def test_chunk_indices_are_sequential(self, source_id):
        chunker = make_chunker()
        chunks = await chunker.chunk(SIMPLE_SOURCE, source_id)

        assert [c.index for c in chunks] == list(range(len(chunks)))

    @pytest.mark.asyncio
    async def test_source_id_is_attached_to_every_chunk(self, source_id):
        chunker = make_chunker()
        chunks = await chunker.chunk(SIMPLE_SOURCE, source_id)

        assert all(c.source == source_id for c in chunks)

    @pytest.mark.asyncio
    async def test_offsets_map_back_to_original_text_exactly(self, source_id):
        chunker = make_chunker()
        chunks = await chunker.chunk(SIMPLE_SOURCE, source_id)

        for c in chunks:
            assert SIMPLE_SOURCE[c.start_offset : c.end_offset] == c.text

    @pytest.mark.asyncio
    async def test_offsets_correct_with_multibyte_unicode_characters(self, source_id):
        # Byte offsets from tree-sitter and Python character offsets diverge
        # once multibyte characters appear. This guards the char/byte offset
        # tracking used when building chunks from spans.
        chunker = make_chunker()
        chunks = await chunker.chunk(UNICODE_SOURCE, source_id)

        assert len(chunks) == 2
        for c in chunks:
            assert UNICODE_SOURCE[c.start_offset : c.end_offset] == c.text


# ---------------------------------------------------------------------------
# Empty / degenerate input
# ---------------------------------------------------------------------------


class TestEmptyInput:

    @pytest.mark.asyncio
    async def test_empty_string_returns_no_chunks(self, source_id):
        chunker = make_chunker()
        chunks = await chunker.chunk("", source_id)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_no_chunks(self, source_id):
        chunker = make_chunker()
        chunks = await chunker.chunk("   \n\t  \n", source_id)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_empty_input_logs_warning(self, source_id, mock_logger):
        chunker = make_chunker()
        await chunker.chunk("", source_id)
        mock_logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# Fallback behavior
# ---------------------------------------------------------------------------


class TestFallback:

    @pytest.mark.asyncio
    async def test_parse_failure_uses_fallback_chunker(
        self, source_id, fallback_chunker
    ):
        expected = [
            Chunk(
                text="fallback", index=0, source=source_id, start_offset=0, end_offset=8
            )
        ]
        fallback_chunker.chunk.return_value = expected
        chunker = make_chunker(fallback_chunker=fallback_chunker)

        with patch(
            "src.rag.services.chunk.code_aware.get_parser",
            side_effect=RuntimeError("no grammar for language"),
        ):
            chunks = await chunker.chunk(SIMPLE_SOURCE, source_id)

        fallback_chunker.chunk.assert_awaited_once()
        assert chunks[0].text == "fallback"

    @pytest.mark.asyncio
    async def test_mostly_error_tree_uses_fallback_chunker(
        self, source_id, fallback_chunker
    ):
        fallback_chunker.chunk.return_value = [
            Chunk(
                text=BROKEN_SOURCE,
                index=0,
                source=source_id,
                start_offset=0,
                end_offset=len(BROKEN_SOURCE),
            )
        ]
        chunker = make_chunker(fallback_chunker=fallback_chunker, error_threshold=0.1)

        chunks = await chunker.chunk(BROKEN_SOURCE, source_id)

        fallback_chunker.chunk.assert_awaited_once()
        assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_fallback_chunks_get_default_node_type_and_language(
        self, source_id, fallback_chunker
    ):
        fallback_chunker.chunk.return_value = [
            Chunk(text="x = 1", index=0, source=source_id, start_offset=0, end_offset=5)
        ]
        chunker = make_chunker(fallback_chunker=fallback_chunker)

        with patch(
            "src.rag.services.chunk.code_aware.get_parser",
            side_effect=RuntimeError("boom"),
        ):
            chunks = await chunker.chunk(SIMPLE_SOURCE, source_id)

        assert chunks[0].metadata["node_type"] == "fallback_text"
        assert chunks[0].metadata["language"] == "python"

    @pytest.mark.asyncio
    async def test_fallback_does_not_overwrite_existing_metadata(
        self, source_id, fallback_chunker
    ):
        fallback_chunker.chunk.return_value = [
            Chunk(
                text="x = 1",
                index=0,
                source=source_id,
                start_offset=0,
                end_offset=5,
                metadata={"node_type": "already_set"},
            )
        ]
        chunker = make_chunker(fallback_chunker=fallback_chunker)

        with patch(
            "src.rag.services.chunk.code_aware.get_parser",
            side_effect=RuntimeError("boom"),
        ):
            chunks = await chunker.chunk(SIMPLE_SOURCE, source_id)

        assert chunks[0].metadata["node_type"] == "already_set"

    @pytest.mark.asyncio
    async def test_missing_fallback_chunker_raises_expected_error(self, source_id):
        chunker = make_chunker(fallback_chunker=None)

        with patch(
            "src.rag.services.chunk.code_aware.get_parser",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(Exception):
                await chunker.chunk(SIMPLE_SOURCE, source_id)

    @pytest.mark.asyncio
    async def test_parse_failure_logs_error(
        self, source_id, fallback_chunker, mock_logger
    ):
        chunker = make_chunker(fallback_chunker=fallback_chunker)

        with patch(
            "src.rag.services.chunk.code_aware.get_parser",
            side_effect=RuntimeError("boom"),
        ):
            await chunker.chunk(SIMPLE_SOURCE, source_id)

        mock_logger.exception.assert_called_once()


# ---------------------------------------------------------------------------
# min_chunk_size merging
# ---------------------------------------------------------------------------


class TestMinChunkSizeMerging:

    @pytest.mark.asyncio
    async def test_small_trailing_chunk_merges_into_previous(self, source_id):
        source = "def add(a, b):\n    return a + b\n\nx = 1\n"
        chunker = make_chunker(min_chunk_size=20)

        chunks = await chunker.chunk(source, source_id)

        assert len(chunks) == 1
        assert "x = 1" in chunks[0].text
        assert "def add" in chunks[0].text

    @pytest.mark.asyncio
    async def test_small_leading_chunk_merges_into_next(self, source_id):
        # Guards the fix for the leading-chunk case, which the original
        # merge pass skipped because there was no earlier chunk to fold into.
        source = "x = 1\n\ndef add(a, b):\n    return a + b\n"
        chunker = make_chunker(min_chunk_size=20)

        chunks = await chunker.chunk(source, source_id)

        assert len(chunks) == 1
        assert "x = 1" in chunks[0].text
        assert "def add" in chunks[0].text

    @pytest.mark.asyncio
    async def test_min_chunk_size_zero_disables_merging(self, source_id):
        source = "x = 1\n\ndef add(a, b):\n    return a + b\n"
        chunker = make_chunker(min_chunk_size=0)

        chunks = await chunker.chunk(source, source_id)

        assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_merged_chunk_text_matches_offsets_exactly(self, source_id):
        source = "x = 1\n\ndef add(a, b):\n    return a + b\n\ny = 2\n"
        chunker = make_chunker(min_chunk_size=20)

        chunks = await chunker.chunk(source, source_id)

        for c in chunks:
            assert source[c.start_offset : c.end_offset] == c.text

    @pytest.mark.asyncio
    async def test_custom_length_function_is_used_for_size_check(self, source_id):
        # A length_function that always returns 0 makes every chunk look
        # "too small", so everything should collapse into one chunk.
        chunker = make_chunker(min_chunk_size=1, length_function=lambda s: 0)

        chunks = await chunker.chunk(SIMPLE_SOURCE, source_id)

        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# max_lines_per_chunk splitting
# ---------------------------------------------------------------------------


class TestMaxLinesPerChunk:

    @pytest.mark.asyncio
    async def test_oversized_function_with_no_nested_matches_kept_whole(
        self, source_id
    ):
        chunker = make_chunker(max_lines_per_chunk=5)

        chunks = await chunker.chunk(LONG_FUNCTION_SOURCE, source_id)

        assert len(chunks) == 1
        assert chunks[0].metadata["node_type"] == "function_definition"

    @pytest.mark.asyncio
    async def test_oversized_function_with_nested_functions_splits_further(
        self, source_id
    ):
        chunker = make_chunker(max_lines_per_chunk=3)

        chunks = await chunker.chunk(LONG_FUNCTION_WITH_NESTED, source_id)

        node_types = [c.metadata["node_type"] for c in chunks]
        assert node_types.count("function_definition") >= 2


# ---------------------------------------------------------------------------
# error_threshold behavior
# ---------------------------------------------------------------------------


class TestErrorThreshold:

    @pytest.mark.asyncio
    async def test_valid_source_does_not_trigger_fallback(
        self, source_id, fallback_chunker
    ):
        chunker = make_chunker(fallback_chunker=fallback_chunker, error_threshold=0.5)

        await chunker.chunk(SIMPLE_SOURCE, source_id)

        fallback_chunker.chunk.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_threshold_zero_is_strict_about_any_error_node(
        self, source_id, fallback_chunker
    ):
        chunker = make_chunker(fallback_chunker=fallback_chunker, error_threshold=0.0)

        await chunker.chunk(BROKEN_SOURCE, source_id)

        fallback_chunker.chunk.assert_awaited_once()


# ---------------------------------------------------------------------------
# chunk_stream (inherited from the Chunker base class)
# ---------------------------------------------------------------------------


class TestChunkStream:

    @pytest.mark.asyncio
    async def test_chunk_stream_joins_segments_and_sets_page_and_offsets(
        self, source_id
    ):
        # The second segment uses separator="" so the joined text is the
        # original source with no extra blank lines. The function node ends
        # before the trailing newline, which becomes a blank span and is
        # dropped.
        chunker = make_chunker()
        expected = "def add(a, b):\n    return a + b"

        async def segments():
            yield Segment(text="def add(a, b):\n", page=1)
            yield Segment(text="    return a + b\n", page=2, separator="")

        results = [c async for c in chunker.chunk_stream(segments(), source_id)]

        assert len(results) == 1
        assert results[0].text == expected
        assert (results[0].start_offset, results[0].end_offset) == (0, len(expected))
        assert results[0].index == 0
        assert results[0].metadata["page"] == 1
        assert results[0].metadata["node_type"] == "function_definition"


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestConfigValidation:

    def test_error_threshold_above_one_is_rejected(self):
        with pytest.raises(Exception):
            CodeAwareChunkerConfig(error_threshold=1.5)

    def test_error_threshold_below_zero_is_rejected(self):
        with pytest.raises(Exception):
            CodeAwareChunkerConfig(error_threshold=-0.1)

    def test_max_lines_per_chunk_zero_is_rejected(self):
        with pytest.raises(Exception):
            CodeAwareChunkerConfig(max_lines_per_chunk=0)
