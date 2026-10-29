"""
This module defines the contract for all chunker classes.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.config.configs import settings
from src.rag.services.extract.extractors.extractor import Segment


class ChunkerConfig(BaseModel):
    """
    Configuration for the chunking process.
    """

    model_config = ConfigDict(frozen=True)

    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)
    min_chunk_size: int = Field(default=0, ge=0)
    length_function: Callable[[str], int] = len

    @model_validator(mode="after")
    def _check_sizes(self) -> "ChunkerConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if self.min_chunk_size >= self.chunk_size:
            raise ValueError("min_chunk_size must be smaller than chunk_size")
        return self


@dataclass
class Chunk:
    """
    Represents a chunk of text extracted from a document, along with any
    associated metadata.

    In streamed output, offsets refer to the full extracted text, which is
    the segments joined by their separators.
    """

    text: str
    index: int
    source: UUID
    start_offset: int
    end_offset: int
    metadata: dict[str, Any] = field(default_factory=dict)


class Chunker(ABC):
    """
    Defines the interface for the chunking service, which is responsible for
    breaking down large text documents into smaller, manageable pieces
    known as chunks.
    """

    @abstractmethod
    async def chunk(self, text: str, source_id: UUID) -> list[Chunk]:
        """Chunks the inputted text into smaller pieces."""
        raise NotImplementedError(
            "The method 'chunk' must be implemented by subclasses of Chunker."
        )

    async def chunk_stream(
        self, stream: AsyncIterable[Segment], source_id: UUID
    ) -> AsyncIterator[Chunk]:
        """
        Chunk a stream of segments, yielding chunks as they become ready.

        The last chunk of each flush stays in the buffer, because more text
        may still extend it. Indexes and offsets run across the whole stream.
        """
        flush_chars = settings.rag.STREAM_FLUSH_CHARS

        buffer = ""
        base = 0  # offset of buffer[0] within the full text
        next_index = 0
        pages: list[tuple[int, int | None]] = []  # (offset in buffer, page)

        async for segment in stream:
            if not segment.text:
                continue

            if buffer:
                buffer += segment.separator

            pages.append((len(buffer), segment.page))
            buffer += segment.text

            if len(buffer) < flush_chars:
                continue

            chunks = await self.chunk(buffer, source_id=source_id)

            if len(chunks) < 2:
                continue  # wait for more text

            for chunk in chunks[:-1]:
                yield _place(chunk, base, next_index, pages)
                next_index += 1

            cut = chunks[-1].start_offset
            pages = _shift_pages(pages, cut)
            base += cut
            buffer = buffer[cut:]

        if buffer.strip():
            for chunk in await self.chunk(buffer, source_id=source_id):
                yield _place(chunk, base, next_index, pages)
                next_index += 1


def _place(
    chunk: Chunk,
    base: int,
    index: int,
    pages: list[tuple[int, int | None]],
) -> Chunk:
    """Convert buffer-local offsets to stream-wide offsets and set the page."""
    page = _page_at(pages, chunk.start_offset)

    if page is not None:
        chunk.metadata["page"] = page

    chunk.index = index
    chunk.start_offset += base
    chunk.end_offset += base

    return chunk


def _page_at(pages: list[tuple[int, int | None]], offset: int) -> int | None:
    page = None

    for start, value in pages:
        if start > offset:
            break
        page = value

    return page


def _shift_pages(
    pages: list[tuple[int, int | None]], cut: int
) -> list[tuple[int, int | None]]:
    """Re-express page markers for a buffer which now starts at `cut`."""
    current = _page_at(pages, cut)

    return [(0, current)] + [
        (start - cut, page) for start, page in pages if start > cut
    ]
