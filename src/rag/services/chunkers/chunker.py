"""
This module defines the contract for all chunker classes.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID

from pydantic import BaseModel, Field, model_validator, ConfigDict


class ChunkConfig(BaseModel):
    """
    Configuration for the chunking process.
    """

    model_config = ConfigDict(frozen=True)

    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)
    min_chunk_size: int = Field(default=0, ge=0)
    length_function: Callable[[str], int] = len

    @model_validator(mode="after")
    def _check_sizes(self) -> "ChunkConfig":
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
        self, stream: AsyncIterable[str], source_id: UUID
    ) -> AsyncIterator[Chunk]:
        """Chunk a stream of text pieces, yielding chunks as they become ready."""
        buffer = "".join([piece async for piece in stream])
        for c in await self.chunk(buffer, source_id=source_id):
            yield c
