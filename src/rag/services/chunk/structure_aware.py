"""
Structure-aware chunking for Markdown-like documents.

The chunker uses configured heading prefixes to identify document structure.
Sections are merged while they fit within chunk_size. Sections exceeding
chunk_size are delegated to the configured fallback chunker.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from uuid import UUID

from pydantic import Field, field_validator, ConfigDict

from src.exceptions import server_error
from src.rag.services.chunk.chunker import ChunkConfig, Chunker, Chunk


class StructureAwareChunkerConfig(ChunkConfig):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    fallback_chunker: "Chunker | None" = Field(default=None)
    header_levels: list[str] = Field(default_factory=lambda: ["#", "##", "###"])

    @field_validator("header_levels")
    @classmethod
    def _check_header_levels_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("header_levels must contain at least one prefix")
        return value


@dataclass
class _Section:
    text: str
    start_offset: int
    end_offset: int
    header: str | None
    header_level: int | None


_logger = logging.getLogger(__name__)


class StructureAwareChunker(Chunker):
    def __init__(self, config: StructureAwareChunkerConfig):
        self._config = config

    async def chunk(self, text: str, source_id: UUID) -> list[Chunk]:
        if not text or not text.strip():
            _logger.warning("No text provided for chunking")
            return []

        sections = await asyncio.to_thread(self._parse_sections, text)

        chunks: list[Chunk] = []
        pending: list[_Section] = []

        for section in sections:
            section_length = self._config.length_function(section.text)

            if section_length > self._config.chunk_size:
                if pending:
                    chunks.extend(
                        self._build_merged_chunk(
                            pending,
                            source_id=source_id,
                            index=len(chunks),
                        )
                    )
                    pending = []

                fallback_chunks = await self._fallback(
                    section.text,
                    source_id=source_id,
                    start_offset=section.start_offset,
                )

                for fallback_chunk in fallback_chunks:
                    fallback_chunk.index = len(chunks)
                    fallback_chunk.metadata = {
                        **fallback_chunk.metadata,
                        "structure_aware": True,
                        "header": section.header,
                        "header_level": section.header_level,
                        "headers": (
                            [{"title": section.header, "level": section.header_level}]
                            if section.header is not None
                            else []
                        ),
                    }
                    chunks.append(fallback_chunk)

                continue

            if not pending:
                pending.append(section)
                continue

            # pending sections and the current section all tile the
            # document contiguously with no gaps, so the combined
            # candidate can be sliced directly from the source text
            # rather than rebuilt by joining every pending section's
            # text on each iteration.
            candidate = text[pending[0].start_offset : section.end_offset]

            if self._config.length_function(candidate) <= self._config.chunk_size:
                pending.append(section)
            else:
                chunks.extend(
                    self._build_merged_chunk(
                        pending,
                        source_id=source_id,
                        index=len(chunks),
                    )
                )
                pending = [section]

        if pending:
            chunks.extend(
                self._build_merged_chunk(
                    pending,
                    source_id=source_id,
                    index=len(chunks),
                )
            )

        chunks = self._merge_small_chunks(chunks, text, source_id)

        for index, chunk in enumerate(chunks):
            chunk.index = index

        return chunks

    def _parse_sections(self, text: str) -> list[_Section]:
        """
        Split the document into sections starting at configured headings.

        Heading detection only happens at the beginning of a line and ignores
        headings inside fenced Markdown code blocks.
        """
        header_pattern = self._build_header_pattern()

        matches: list[tuple[int, int, str, int]] = []

        in_code_block = False
        code_fence = ""

        for match in re.finditer(r"^.*(?:\n|$)", text, re.MULTILINE):
            line = match.group(0)
            line_without_newline = line.rstrip("\r\n")

            stripped = line_without_newline.lstrip()

            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence = stripped[:3]

                if not in_code_block:
                    in_code_block = True
                    code_fence = fence
                elif fence == code_fence:
                    in_code_block = False
                    code_fence = ""

                continue

            if in_code_block:
                continue

            header_match = header_pattern.match(line_without_newline)

            if header_match is None:
                continue

            level = len(header_match.group("prefix"))
            header = header_match.group("title").strip()

            matches.append(
                (
                    match.start(),
                    match.end(),
                    header,
                    level,
                )
            )

        if not matches:
            return [
                _Section(
                    text=text,
                    start_offset=0,
                    end_offset=len(text),
                    header=None,
                    header_level=None,
                )
            ]

        sections: list[_Section] = []

        first_header_start = matches[0][0]

        # Text before the first heading.
        if first_header_start > 0:
            sections.append(
                _Section(
                    text=text[:first_header_start],
                    start_offset=0,
                    end_offset=first_header_start,
                    header=None,
                    header_level=None,
                )
            )

        for index, (start, _, header, level) in enumerate(matches):
            end = matches[index + 1][0] if index + 1 < len(matches) else len(text)

            sections.append(
                _Section(
                    text=text[start:end],
                    start_offset=start,
                    end_offset=end,
                    header=header,
                    header_level=level,
                )
            )

        return sections

    def _build_header_pattern(self) -> re.Pattern[str]:
        """
        Build a regex for configured Markdown heading prefixes.

        For example:

            ["#", "##", "###"]

        matches:

            # Title
            ## Section
            ### Subsection

        but does not match:

            #### Too deep
            #Title
        """
        prefixes = sorted(
            (re.escape(prefix) for prefix in self._config.header_levels),
            key=len,
            reverse=True,
        )

        prefix_pattern = "|".join(prefixes)

        return re.compile(rf"^(?P<prefix>{prefix_pattern})[ \t]+(?P<title>.+?)\s*$")

    @staticmethod
    def _build_merged_chunk(
        sections: list[_Section],
        source_id: UUID,
        index: int,
    ) -> list[Chunk]:
        if not sections:
            return []

        text = "".join(section.text for section in sections)

        first = sections[0]
        last = sections[-1]

        headers = [
            {
                "title": section.header,
                "level": section.header_level,
            }
            for section in sections
            if section.header is not None
        ]

        return [
            Chunk(
                text=text,
                index=index,
                source=source_id,
                start_offset=first.start_offset,
                end_offset=last.end_offset,
                metadata={
                    "structure_aware": True,
                    "headers": headers,
                    "header": first.header,
                    "header_level": first.header_level,
                },
            )
        ]

    async def _fallback(
        self,
        text: str,
        source_id: UUID,
        start_offset: int,
    ) -> list[Chunk]:
        """
        Delegate oversized sections to the configured fallback chunker.
        """
        if self._config.fallback_chunker is None:
            raise server_error(
                message="Fallback chunker must be provided",
                error_code="FALLBACK_CHUNKER_REQUIRED",
            )

        fallback_chunks = await self._config.fallback_chunker.chunk(
            text,
            source_id=source_id,
        )

        result: list[Chunk] = []

        for chunk in fallback_chunks:
            result.append(
                Chunk(
                    text=chunk.text,
                    index=chunk.index,
                    source=source_id,
                    start_offset=(start_offset + chunk.start_offset),
                    end_offset=(start_offset + chunk.end_offset),
                    metadata=dict(chunk.metadata),
                )
            )

        return result

    def _merge_small_chunks(
        self,
        chunks: list[Chunk],
        text: str,
        source_id: UUID,
    ) -> list[Chunk]:
        """
        Merge chunks below min_chunk_size with adjacent chunks where possible.

        This primarily handles tiny preambles (a short line of text before
        the first heading) or tiny trailing sections created by heading
        boundaries.
        """
        if self._config.min_chunk_size <= 0 or len(chunks) <= 1:
            return chunks

        def combine(prev: Chunk, nxt: Chunk) -> str:
            # Re-slice from the original document rather than
            # concatenating cached chunk text. Chunks handed back by a
            # fallback chunker can have gaps (a blank line the fallback
            # chunker filtered out as empty) or overlap (if the
            # fallback chunker uses chunk_overlap), so naive
            # concatenation can silently drop or duplicate characters
            # relative to the source document.
            return text[prev.start_offset : nxt.end_offset]

        def merge_headers(prev: Chunk, nxt: Chunk) -> list[dict]:
            return prev.metadata.get("headers", []) + nxt.metadata.get("headers", [])

        result: list[Chunk] = []

        for chunk in chunks:
            chunk_size = self._config.length_function(chunk.text)

            if result and chunk_size < self._config.min_chunk_size:
                previous = result[-1]
                combined_text = combine(previous, chunk)

                if (
                    self._config.length_function(combined_text)
                    <= self._config.chunk_size
                ):
                    previous.text = combined_text
                    previous.end_offset = chunk.end_offset
                    previous.metadata["headers"] = merge_headers(previous, chunk)
                    continue

            result.append(chunk)

        # A small first chunk -- the tiny-preamble case this function
        # exists for -- has no earlier chunk to merge into during the
        # pass above, so fold it forward into the chunk that follows it
        # here.
        if len(result) > 1:
            first_size = self._config.length_function(result[0].text)

            if first_size < self._config.min_chunk_size:
                first, second = result[0], result[1]
                combined_text = combine(first, second)

                if (
                    self._config.length_function(combined_text)
                    <= self._config.chunk_size
                ):
                    second.text = combined_text
                    second.start_offset = first.start_offset
                    second.metadata["headers"] = merge_headers(first, second)
                    # The merged range's earliest header now comes from
                    # the chunk folded in, not the one it was folded into.
                    second.metadata["header"] = first.metadata.get("header")
                    second.metadata["header_level"] = first.metadata.get("header_level")
                    result.pop(0)

        for index, chunk in enumerate(result):
            chunk.index = index
            chunk.source = source_id

        return result
