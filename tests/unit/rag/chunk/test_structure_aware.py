"""
Unit tests for StructureAwareChunker.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.exceptions.base import ApiException
from src.rag.services.chunk.chunker import Chunk, Chunker
from src.rag.services.chunk.structure_aware import (
    StructureAwareChunkerConfig,
    StructureAwareChunker,
)
from src.rag.services.extract.extractors.extractor import Segment

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_logger():
    """
    Replace the module-level logger with a plain mock so tests do not depend
    on the real logging setup, and so warning calls can be asserted on.
    """
    with patch("src.rag.services.chunk.structure_aware._logger") as mock_logger:
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


def make_config(**overrides) -> StructureAwareChunkerConfig:
    defaults = dict(chunk_size=1000, chunk_overlap=0, min_chunk_size=0)
    defaults.update(overrides)
    return StructureAwareChunkerConfig(**defaults)


def make_chunker(**overrides) -> StructureAwareChunker:
    return StructureAwareChunker(make_config(**overrides))


def offsets(chunks) -> list[tuple[int, int, str]]:
    return [(c.start_offset, c.end_offset, c.text) for c in chunks]


def make_chunk(text, index, source_id, start, end, metadata=None) -> Chunk:
    return Chunk(
        text=text,
        index=index,
        source=source_id,
        start_offset=start,
        end_offset=end,
        metadata=metadata if metadata is not None else {},
    )


# ---------------------------------------------------------------------------
# Core section merging and splitting
# ---------------------------------------------------------------------------


class TestSectionMergingAndSplitting:

    @pytest.mark.asyncio
    async def test_sections_merge_into_one_chunk_when_combined_fits(self, source_id):
        # "# Title\nBody one.\n" (0-18) and "## Section\nBody two.\n"
        # (18-39) both fit under a large chunk_size, so they combine
        # into a single merged chunk.
        text = "# Title\nBody one.\n## Section\nBody two.\n"
        chunker = make_chunker(chunk_size=1000)

        chunks = await chunker.chunk(text, source_id)

        assert len(chunks) == 1
        assert chunks[0].text == text
        assert (chunks[0].start_offset, chunks[0].end_offset) == (0, len(text))
        assert chunks[0].metadata["headers"] == [
            {"title": "Title", "level": 1},
            {"title": "Section", "level": 2},
        ]
        assert chunks[0].metadata["header"] == "Title"
        assert chunks[0].metadata["header_level"] == 1

    @pytest.mark.asyncio
    async def test_sections_split_into_separate_chunks_when_combined_exceeds(
        self, source_id
    ):
        # Each section is 6 characters ("# A\nx\n" and "# B\ny\n"), so
        # both fit alone under chunk_size=8, but the two combined (12
        # characters) do not, forcing a split between them.
        text = "# A\nx\n# B\ny\n"
        chunker = make_chunker(chunk_size=8)

        chunks = await chunker.chunk(text, source_id)

        assert offsets(chunks) == [
            (0, 6, "# A\nx\n"),
            (6, 12, "# B\ny\n"),
        ]
        assert [c.index for c in chunks] == [0, 1]
        assert all(c.source == source_id for c in chunks)
        assert all(text[c.start_offset : c.end_offset] == c.text for c in chunks)
        assert chunks[0].metadata["headers"] == [{"title": "A", "level": 1}]
        assert chunks[1].metadata["headers"] == [{"title": "B", "level": 1}]


# ---------------------------------------------------------------------------
# Fallback delegation
# ---------------------------------------------------------------------------


class TestFallbackDelegation:

    @pytest.mark.asyncio
    async def test_oversized_section_delegates_to_fallback_with_offsets_and_metadata(
        self, source_id, fallback_chunker
    ):
        # "# Big\nzzzzzzzzzz\n" is 17 characters, over chunk_size=5, so
        # the whole section goes to the fallback chunker.
        text = "# Big\nzzzzzzzzzz\n"
        fallback_chunker.chunk.return_value = [
            make_chunk("# Big\n", 0, source_id, 0, 6),
            make_chunk("zzzzzzzzzz\n", 1, source_id, 6, 17),
        ]
        chunker = make_chunker(chunk_size=5, fallback_chunker=fallback_chunker)

        chunks = await chunker.chunk(text, source_id)

        fallback_chunker.chunk.assert_awaited_once()
        assert offsets(chunks) == [
            (0, 6, "# Big\n"),
            (6, 17, "zzzzzzzzzz\n"),
        ]
        assert [c.index for c in chunks] == [0, 1]
        for c in chunks:
            assert c.source == source_id
            assert c.metadata["structure_aware"] is True
            assert c.metadata["header"] == "Big"
            assert c.metadata["header_level"] == 1
            # Guards the fix: fallback chunks carry the same "headers"
            # list shape as section-merged chunks, so header info is not
            # dropped if the chunk later merges with another.
            assert c.metadata["headers"] == [{"title": "Big", "level": 1}]

    @pytest.mark.asyncio
    async def test_fallback_offsets_shift_by_section_start(
        self, source_id, fallback_chunker
    ):
        # The first section "# A\nx\n" (0-6) fits under chunk_size=8. The
        # second section "# Big\nzzzzzzzzzz\n" (6-23) does not, so it goes
        # to the fallback chunker, whose relative offsets must shift by 6.
        text = "# A\nx\n# Big\nzzzzzzzzzz\n"
        fallback_chunker.chunk.return_value = [
            make_chunk("# Big\n", 0, source_id, 0, 6),
            make_chunk("zzzzzzzzzz\n", 1, source_id, 6, 17),
        ]
        chunker = make_chunker(chunk_size=8, fallback_chunker=fallback_chunker)

        chunks = await chunker.chunk(text, source_id)

        assert offsets(chunks) == [
            (0, 6, "# A\nx\n"),
            (6, 12, "# Big\n"),
            (12, 23, "zzzzzzzzzz\n"),
        ]
        assert [c.index for c in chunks] == [0, 1, 2]
        assert all(text[c.start_offset : c.end_offset] == c.text for c in chunks)

    @pytest.mark.asyncio
    async def test_fallback_chunker_not_configured_raises_api_exception(
        self, source_id
    ):
        # No headings, so the whole 20-character document is one section
        # that exceeds chunk_size=5 and needs a fallback chunker that was
        # never configured.
        text = "a" * 20
        chunker = make_chunker(chunk_size=5, fallback_chunker=None)

        with pytest.raises(ApiException):
            await chunker.chunk(text, source_id)


# ---------------------------------------------------------------------------
# Heading detection edge cases
# ---------------------------------------------------------------------------


class TestHeadingDetection:

    @pytest.mark.asyncio
    async def test_headers_inside_fenced_code_blocks_are_ignored(self, source_id):
        text = (
            "# Real Header\n"
            "```\n"
            "# Not a header\n"
            "```\n"
            "~~~\n"
            "## Also not\n"
            "~~~\n"
            "# Another Real\n"
        )
        chunker = make_chunker(chunk_size=10000)

        chunks = await chunker.chunk(text, source_id)

        assert len(chunks) == 1
        assert chunks[0].metadata["headers"] == [
            {"title": "Real Header", "level": 1},
            {"title": "Another Real", "level": 1},
        ]

    @pytest.mark.asyncio
    async def test_header_deeper_than_configured_levels_is_ignored(self, source_id):
        text = "#### TooDeep\nBody\n"
        chunker = make_chunker(chunk_size=10000, header_levels=["#", "##", "###"])

        chunks = await chunker.chunk(text, source_id)

        assert len(chunks) == 1
        assert chunks[0].metadata["header"] is None
        assert chunks[0].metadata["headers"] == []

    @pytest.mark.asyncio
    async def test_header_prefix_without_following_space_is_ignored(self, source_id):
        text = "#Title\nBody\n"
        chunker = make_chunker(chunk_size=10000)

        chunks = await chunker.chunk(text, source_id)

        assert len(chunks) == 1
        assert chunks[0].metadata["header"] is None

    @pytest.mark.asyncio
    async def test_indented_hash_line_is_not_treated_as_a_header(self, source_id):
        text = "  # Indented\nBody\n"
        chunker = make_chunker(chunk_size=10000)

        chunks = await chunker.chunk(text, source_id)

        assert len(chunks) == 1
        assert chunks[0].metadata["header"] is None

    @pytest.mark.asyncio
    async def test_text_before_first_header_becomes_a_headerless_section(
        self, source_id
    ):
        # "Intro\n" (0-6) has no heading. "# A\nx\n" (6-12) does. With
        # chunk_size=8 they cannot combine (12 characters), so the
        # preamble stands alone with no header metadata.
        text = "Intro\n# A\nx\n"
        chunker = make_chunker(chunk_size=8)

        chunks = await chunker.chunk(text, source_id)

        assert offsets(chunks) == [
            (0, 6, "Intro\n"),
            (6, 12, "# A\nx\n"),
        ]
        assert chunks[0].metadata["header"] is None
        assert chunks[0].metadata["headers"] == []
        assert chunks[1].metadata["header"] == "A"

    @pytest.mark.asyncio
    async def test_windows_line_endings_headers_still_detected(self, source_id):
        text = "# A\r\nbody\r\n# B\r\nbody2\r\n"
        chunker = make_chunker(chunk_size=10000)

        chunks = await chunker.chunk(text, source_id)

        assert len(chunks) == 1
        assert chunks[0].metadata["headers"] == [
            {"title": "A", "level": 1},
            {"title": "B", "level": 1},
        ]


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
# Config validation
# ---------------------------------------------------------------------------


class TestConfigValidation:

    def test_empty_header_levels_is_rejected(self):
        with pytest.raises(ValidationError):
            StructureAwareChunkerConfig(
                chunk_size=100, chunk_overlap=0, header_levels=[]
            )

    def test_default_header_levels(self):
        config = StructureAwareChunkerConfig(chunk_size=100, chunk_overlap=0)
        assert config.header_levels == ["#", "##", "###"]


# ---------------------------------------------------------------------------
# _merge_small_chunks, tested directly
# ---------------------------------------------------------------------------


class TestMergeSmallChunks:

    def test_trailing_small_chunk_merges_into_previous(self, source_id):
        chunker = make_chunker(min_chunk_size=5, chunk_size=100)
        text = "AAAAAAAAAAbb"
        chunks = [
            make_chunk(
                "AAAAAAAAAA",
                0,
                source_id,
                0,
                10,
                metadata={
                    "headers": [{"title": "H1", "level": 1}],
                    "header": "H1",
                    "header_level": 1,
                },
            ),
            make_chunk(
                "bb",
                1,
                source_id,
                10,
                12,
                metadata={
                    "headers": [{"title": "H2", "level": 1}],
                    "header": "H2",
                    "header_level": 1,
                },
            ),
        ]

        result = chunker._merge_small_chunks(chunks, text, source_id)

        assert len(result) == 1
        assert (result[0].start_offset, result[0].end_offset) == (0, 12)
        assert result[0].text == text
        assert result[0].metadata["headers"] == [
            {"title": "H1", "level": 1},
            {"title": "H2", "level": 1},
        ]
        # A trailing merge keeps the surviving chunk's own header and
        # header_level. Only the "headers" list is combined.
        assert result[0].metadata["header"] == "H1"
        assert result[0].metadata["header_level"] == 1

    def test_leading_small_chunk_merges_into_next_and_reassigns_header(self, source_id):
        # Guards the fix: a small first chunk has no earlier chunk to
        # merge into during the forward pass. The surviving chunk takes
        # the folded-in chunk's header and header_level, since that
        # content now starts the merged range.
        chunker = make_chunker(min_chunk_size=5, chunk_size=100)
        text = "aaAAAAAAAAAA"
        chunks = [
            make_chunk(
                "aa",
                0,
                source_id,
                0,
                2,
                metadata={
                    "headers": [{"title": "H1", "level": 1}],
                    "header": "H1",
                    "header_level": 1,
                },
            ),
            make_chunk(
                "AAAAAAAAAA",
                1,
                source_id,
                2,
                12,
                metadata={
                    "headers": [{"title": "H2", "level": 2}],
                    "header": "H2",
                    "header_level": 2,
                },
            ),
        ]

        result = chunker._merge_small_chunks(chunks, text, source_id)

        assert len(result) == 1
        assert (result[0].start_offset, result[0].end_offset) == (0, 12)
        assert result[0].text == text
        assert result[0].metadata["headers"] == [
            {"title": "H1", "level": 1},
            {"title": "H2", "level": 2},
        ]
        assert result[0].metadata["header"] == "H1"
        assert result[0].metadata["header_level"] == 1

    def test_merge_blocked_when_combined_would_exceed_chunk_size(self, source_id):
        chunker = make_chunker(min_chunk_size=5, chunk_size=9)
        text = "a" * 10
        chunks = [
            make_chunk("a" * 8, 0, source_id, 0, 8, metadata={"headers": []}),
            make_chunk("aa", 1, source_id, 8, 10, metadata={"headers": []}),
        ]

        result = chunker._merge_small_chunks(chunks, text, source_id)

        assert len(result) == 2
        assert (result[0].start_offset, result[0].end_offset) == (0, 8)
        assert (result[1].start_offset, result[1].end_offset) == (8, 10)

    def test_merge_reslices_from_source_text_across_a_gap(self, source_id):
        # A fallback chunker can drop a blank region between two chunks.
        # Merging must re-slice from the source text so the gap content
        # is kept, instead of concatenating the two cached texts.
        chunker = make_chunker(min_chunk_size=5, chunk_size=100)
        text = "AAAAAAAA  bb"
        chunks = [
            make_chunk("AAAAAAAA", 0, source_id, 0, 8, metadata={"headers": []}),
            make_chunk("bb", 1, source_id, 10, 12, metadata={"headers": []}),
        ]

        result = chunker._merge_small_chunks(chunks, text, source_id)

        assert len(result) == 1
        assert result[0].text == "AAAAAAAA  bb"
        assert text[result[0].start_offset : result[0].end_offset] == result[0].text

    def test_min_chunk_size_zero_returns_chunks_unchanged(self, source_id):
        chunker = make_chunker(min_chunk_size=0)
        chunks = [
            make_chunk("a", 0, source_id, 0, 1),
            make_chunk("b", 1, source_id, 1, 2),
        ]

        result = chunker._merge_small_chunks(chunks, "ab", source_id)

        assert result == chunks

    def test_single_chunk_returns_unchanged(self, source_id):
        chunker = make_chunker(min_chunk_size=100, chunk_size=200)
        chunks = [make_chunk("a", 0, source_id, 0, 1)]

        result = chunker._merge_small_chunks(chunks, "a", source_id)

        assert result == chunks


# ---------------------------------------------------------------------------
# chunk_stream (inherited from the Chunker base class)
# ---------------------------------------------------------------------------


class TestChunkStream:

    @pytest.mark.asyncio
    async def test_chunk_stream_joins_segments_and_sets_page_and_offsets(
        self, source_id
    ):
        # The second segment uses separator="" so the joined text is
        # "# Title\nBody.\n" with no blank line, and the heading stays at
        # the start of a line.
        chunker = make_chunker(chunk_size=1000)
        expected = "# Title\nBody.\n"

        async def segments():
            yield Segment(text="# Title\n", page=1)
            yield Segment(text="Body.\n", page=2, separator="")

        results = [c async for c in chunker.chunk_stream(segments(), source_id)]

        assert len(results) == 1
        assert results[0].text == expected
        assert (results[0].start_offset, results[0].end_offset) == (0, len(expected))
        assert results[0].index == 0
        assert results[0].metadata["page"] == 1
        assert results[0].metadata["header"] == "Title"
