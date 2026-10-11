"""
Responsible for creating and managing chunkers.
"""

import logging

from pydantic import BaseModel, Field, model_validator

from src.rag.services.chunk.chunker import Chunker
from src.rag.services.chunk.code_aware import (
    CodeAwareChunker,
    CodeAwareChunkerConfig,
)
from src.rag.services.chunk.recursive_character_splitter import (
    RecursiveCharChunkerConfig,
    RecursiveCharacterSplittingChunker,
)
from src.rag.services.chunk.sentence_based import (
    SentenceBasedChunker,
    SentenceChunkerConfig,
)
from src.rag.services.chunk.structure_aware import (
    StructureAwareChunker,
    StructureAwareChunkerConfig,
)

_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {".txt", ".text", ".docx", ".pdf", ".html"}
)

"""
Defines the mapping of file extensions to their corresponding programming
languages and the node types used for splitting code into chunks.

This configuration is used by the CodeAwareChunker to determine how to
process different code files based on their extensions.
"""
_CODE_LANGUAGE_CONFIGS: dict[frozenset[str], tuple[str, list[str]]] = {
    frozenset({".py"}): (
        "python",
        ["function_definition", "class_definition"],
    ),
    frozenset({".js", ".jsx"}): (
        "javascript",
        ["function_declaration", "class_declaration", "method_definition"],
    ),
    frozenset({".ts"}): (
        "typescript",
        ["function_declaration", "class_declaration", "method_definition"],
    ),
    frozenset({".tsx"}): (
        "tsx",
        ["function_declaration", "class_declaration", "method_definition"],
    ),
    frozenset({".java"}): (
        "java",
        ["method_declaration", "class_declaration"],
    ),
    frozenset({".go"}): (
        "go",
        ["function_declaration", "method_declaration", "type_declaration"],
    ),
}


class ChunkerBuildConfig(BaseModel):
    """Configuration for the ChunkerFactory."""

    chunk_size: int = Field(ge=400, lt=2000, default=1500)
    chunk_overlap: int = Field(ge=0, lt=500, default=150)
    code_max_lines_per_chunk: int = Field(ge=1, default=200)

    @model_validator(mode="after")
    def _check_overlap_smaller_than_chunk_size(self) -> "ChunkerBuildConfig":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


_logger = logging.getLogger(__name__)


class ChunkerFactory:
    def __init__(self, config: ChunkerBuildConfig):
        self._config = config
        self._chunkers: dict[str, Chunker] = {}

        self._default_chunker: Chunker = RecursiveCharacterSplittingChunker(
            RecursiveCharChunkerConfig(
                chunk_size=self._config.chunk_size,
                chunk_overlap=self._config.chunk_overlap,
                min_chunk_size=0,  # TODO: Review this value!
            )
        )

    def get_chunker(self, extension: str) -> Chunker:
        """
        Returns the appropriate chunker based on the provided criteria.
        """
        normalized_extension = self._normalize_extension(extension)

        if normalized_extension in self._chunkers:
            return self._chunkers[normalized_extension]

        chunker = self._build_chunker_for_text_file(
            normalized_extension
        ) or self._build_chunker_for_code_file(normalized_extension)

        if chunker is not None:
            self._chunkers[normalized_extension] = chunker
            return chunker

        _logger.debug(
            f"No specific chunker found for extension '{normalized_extension}'. "
            f"Using default chunker."
        )

        return self._default_chunker

    def _build_chunker_for_code_file(self, normalized_extension: str) -> Chunker | None:
        """
        Builds a CodeAwareChunker for the given code file extension.
        Expects an already-normalized extension.
        """
        for extensions, (language, split_node_types) in _CODE_LANGUAGE_CONFIGS.items():
            if normalized_extension in extensions:
                return CodeAwareChunker(
                    CodeAwareChunkerConfig(
                        language=language,
                        split_node_types=split_node_types,
                        fallback_chunker=self._default_chunker,
                        max_lines_per_chunk=self._config.code_max_lines_per_chunk,
                    )
                )

        return None

    def _build_chunker_for_text_file(self, normalized_extension: str) -> Chunker | None:
        """
        Builds a chunker for the given text file extension, either a
        StructureAwareChunker for Markdown files or a SentenceBasedChunker for
        other text files. Expects an already-normalized extension.
        """
        if normalized_extension in ".md":
            return StructureAwareChunker(
                StructureAwareChunkerConfig(
                    chunk_size=self._config.chunk_size,
                    chunk_overlap=self._config.chunk_overlap,
                    fallback_chunker=self._default_chunker,
                    min_chunk_size=0,  # TODO: Choose a better value later!
                    header_levels=["#", "##", "###", "####"],
                )
            )

        if normalized_extension in _TEXT_EXTENSIONS:
            return SentenceBasedChunker(
                SentenceChunkerConfig(
                    chunk_size=self._config.chunk_size,
                    chunk_overlap=self._config.chunk_overlap,
                    min_chunk_size=0,  # TODO: Choose a better value later!
                    max_sentences_per_chunk=5,
                    # TODO: Choose a better value later!
                )
            )

        return None

    @staticmethod
    def _normalize_extension(extension: str) -> str:
        ext = extension.strip().lower()
        if ext and not ext.startswith("."):
            ext = f".{ext}"
        return ext
