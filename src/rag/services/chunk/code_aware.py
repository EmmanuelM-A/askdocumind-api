"""
Responsible for chunking source code files in a way that respects the
structure of the code, using tree-sitter to parse the code into an AST and
splitting it into chunks based on top-level constructs like functions and
classes.
"""

import asyncio
import logging
from collections.abc import Callable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from tree_sitter import Node
from tree_sitter_language_pack import get_parser

from src.exceptions import server_error
from src.rag.services.chunk.chunker import Chunk, Chunker
from src.rag.services.chunk.utils import merge_undersized_chunks

_logger = logging.getLogger(__name__)


class CodeAwareChunkerConfig(BaseModel):
    """
    Configuration for the CodeAwareChunker. This chunker splits on syntax
    boundaries (functions, classes), not on a fixed size or a sliding
    window, so it has no chunk_size or chunk_overlap setting.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    min_chunk_size: int = Field(default=0, ge=0)
    length_function: Callable[[str], int] = len
    language: str = Field(default="python")
    split_node_types: list[str] = Field(
        default_factory=lambda: ["function_definition", "class_definition"]
    )
    max_lines_per_chunk: int | None = Field(default=None, ge=1)
    fallback_chunker: "Chunker | None" = Field(default=None)
    error_threshold: float = Field(default=0.5, ge=0, le=1)


class CodeAwareChunker(Chunker):

    def __init__(self, config: CodeAwareChunkerConfig):
        self._config = config

    async def chunk(self, text: str, source_id: UUID) -> list[Chunk]:
        if not text or not text.strip():
            _logger.warning("No text provided for chunking")
            return []

        source_bytes = text.encode("utf-8")

        try:
            parser = get_parser(self._config.language)
            tree = await asyncio.to_thread(parser.parse, source_bytes)
        except Exception as e:
            _logger.exception(
                "Failed to parse source code with tree-sitter", exc_info=e
            )
            return await self._fallback_chunker(text, source_id=source_id)

        root = tree.root_node

        if self._is_tree_unusable(root):
            _logger.warning(
                "Tree-sitter parse tree is mostly ERROR nodes - Using fallback chunker"
            )
            return await self._fallback_chunker(text, source_id=source_id)

        spans = self._split_top_level(root)
        chunks = self._spans_to_chunks(spans, source_bytes, source_id=source_id)

        return merge_undersized_chunks(
            chunks=chunks,
            text=text,
            min_chunk_size=self._config.min_chunk_size,
            length_function=self._config.length_function,
        )

    # ---------------------- Tree-sitter AST Splitting ----------------------

    def _is_tree_unusable(self, root: Node) -> bool:
        """
        Returns True if the tree is mostly ERROR nodes, meaning the AST
        cannot be trusted, and we should fall back to line-based chunking.
        """
        top_level = root.children

        if not top_level:
            return False

        error_count = sum(1 for n in top_level if n.type == "ERROR" or n.has_error)

        return (error_count / len(top_level)) > self._config.error_threshold

    def _split_top_level(self, root: Node) -> list[tuple[int, int, str | None]]:
        """
        Finds split_node_types matches among root's immediate children, and
        treats any grammar wrapper nodes in between (e.g. Python's `block`,
        or a `suite`/`body` node in other grammars) as transparent.
        """
        return self._split_node_children(root)

    def _split_node_children(self, node: Node) -> list[tuple[int, int, str | None]]:
        """
        Splits a node's children into spans based on split_node_types matches,
        and recursively splits any matches that are too big themselves.
        """
        matches = self._find_split_nodes(node)

        spans: list[tuple[int, int, str | None]] = []
        cursor = node.start_byte

        for match in matches:
            if match.start_byte > cursor:
                spans.append((cursor, match.start_byte, None))

            spans.extend(self._split_node_if_too_big(match))
            cursor = match.end_byte

        if cursor < node.end_byte:
            spans.append((cursor, node.end_byte, None))

        return spans

    def _find_split_nodes(self, node: Node) -> list[Node]:
        """
        DFS in document order for the nearest matching descendant nodes,
        without descending into a node once it matches (its own oversized
        handling happens separately in _split_node_if_too_big).
        """
        matches: list[Node] = []
        for child in node.children:
            if child.type in self._config.split_node_types:
                matches.append(child)
            else:
                matches.extend(self._find_split_nodes(child))
        return matches

    def _split_node_if_too_big(self, node: Node) -> list[tuple[int, int, str | None]]:
        if self._config.max_lines_per_chunk is None:
            return [(node.start_byte, node.end_byte, node.type)]

        line_count = node.end_point[0] - node.start_point[0] + 1
        if line_count <= self._config.max_lines_per_chunk:
            return [(node.start_byte, node.end_byte, node.type)]

        nested_matches = self._find_split_nodes(node)
        if not nested_matches:
            # Oversized node with nothing to split further (e.g. one huge
            # function body). Keep it whole rather than lose it.
            return [(node.start_byte, node.end_byte, node.type)]

        return self._split_node_children(node)

    def _spans_to_chunks(
        self,
        spans: list[tuple[int, int, str | None]],
        source_bytes: bytes,
        source_id: UUID,
    ) -> list[Chunk]:
        """
        Convert a list of byte spans into a list of chunks.
        """
        chunks: list[Chunk] = []
        char_offset = 0
        byte_offset = 0

        for start_byte, end_byte, node_type in spans:
            # Advance char_offset by only the gap since the last span, instead
            # of re-decoding the file from the start on every iteration.
            char_offset += len(source_bytes[byte_offset:start_byte].decode("utf-8"))
            byte_offset = start_byte

            chunk_text = source_bytes[start_byte:end_byte].decode("utf-8")
            if not chunk_text.strip():
                char_offset += len(chunk_text)
                byte_offset = end_byte
                continue

            start_char = char_offset
            end_char = start_char + len(chunk_text)
            char_offset = end_char
            byte_offset = end_byte

            chunks.append(
                Chunk(
                    text=chunk_text,
                    index=len(chunks),
                    source=source_id,
                    start_offset=start_char,
                    end_offset=end_char,
                    metadata={
                        "node_type": node_type or "preamble",
                        "language": self._config.language,
                    },
                )
            )
        return chunks

    # ------------------------- Fallback Chunker -------------------------

    async def _fallback_chunker(self, text: str, source_id: UUID) -> list[Chunk]:
        """
        Backup chunker for when tree-sitter fails to parse the source code,
        or the parse tree is mostly ERROR nodes.
        """

        if self._config.fallback_chunker is None:
            raise server_error(
                message="Fallback chunker must be provided",
                error_code="FALLBACK_CHUNKER_REQUIRED",
            )

        chunks = await self._config.fallback_chunker.chunk(
            text=text, source_id=source_id
        )

        for c in chunks:
            c.metadata.setdefault("node_type", "fallback_text")
            c.metadata.setdefault("language", self._config.language)

        return merge_undersized_chunks(
            chunks=chunks,
            text=text,
            min_chunk_size=self._config.min_chunk_size,
            length_function=self._config.length_function,
        )
