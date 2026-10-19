"""
Unit tests for ChunkerFactory.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.rag.services.chunk.chunker import Chunker
from src.rag.services.chunk.factory import ChunkerBuildConfig, ChunkerFactory


@pytest.fixture
def mock_chunker_classes():
    """
    Patches the four concrete chunker classes factory.py constructs.
    """
    with patch("src.rag.services.chunk.factory.CodeAwareChunker") as code_cls, patch(
        "src.rag.services.chunk.factory.StructureAwareChunker"
    ) as structure_cls, patch(
        "src.rag.services.chunk.factory.SentenceBasedChunker"
    ) as sentence_cls, patch(
        "src.rag.services.chunk.factory.RecursiveCharacterSplittingChunker"
    ) as rcs_cls:
        for cls_mock in (code_cls, structure_cls, sentence_cls, rcs_cls):
            cls_mock.side_effect = lambda *a, **kw: MagicMock(spec=Chunker)

        yield {
            "code": code_cls,
            "structure": structure_cls,
            "sentence": sentence_cls,
            "rcs": rcs_cls,
        }


def make_factory(mock_chunker_classes, **overrides) -> ChunkerFactory:
    config = ChunkerBuildConfig(**overrides)
    return ChunkerFactory(config)


# ---------------------------------------------------------------------------
# Correct chunker selection per extension
# ---------------------------------------------------------------------------


class TestChunkerSelection:

    def test_python_uses_code_aware_chunker_with_correct_language(
        self, mock_chunker_classes
    ):
        factory = make_factory(mock_chunker_classes)

        factory.get_chunker(".py")

        mock_chunker_classes["code"].assert_called_once()
        config = mock_chunker_classes["code"].call_args.args[0]
        assert config.language == "python"
        assert config.max_lines_per_chunk == 200
        assert config.fallback_chunker is factory._default_chunker

    def test_go_uses_code_aware_chunker_with_correct_language(
        self, mock_chunker_classes
    ):
        factory = make_factory(mock_chunker_classes)

        factory.get_chunker(".go")

        config = mock_chunker_classes["code"].call_args.args[0]
        assert config.language == "go"

    def test_typescript_and_tsx_use_different_language_configs(
        self, mock_chunker_classes
    ):
        factory = make_factory(mock_chunker_classes)

        ts_chunker = factory.get_chunker(".ts")
        tsx_chunker = factory.get_chunker(".tsx")

        assert mock_chunker_classes["code"].call_count == 2
        ts_config = mock_chunker_classes["code"].call_args_list[0].args[0]
        tsx_config = mock_chunker_classes["code"].call_args_list[1].args[0]
        assert ts_config.language == "typescript"
        assert tsx_config.language == "tsx"
        assert ts_chunker is not tsx_chunker

    def test_markdown_extension_uses_structure_aware_chunker(
        self, mock_chunker_classes
    ):
        factory = make_factory(mock_chunker_classes)

        factory.get_chunker(".md")

        mock_chunker_classes["structure"].assert_called_once()
        mock_chunker_classes["sentence"].assert_not_called()

    def test_markdown_check_is_an_exact_match_not_a_substring_match(
        self, mock_chunker_classes
    ):
        # Regression test: the check used to be `extension in ".md"`, so any
        # substring of ".md" (".", ".m", "m") was routed to
        # StructureAwareChunker. Only ".md" itself should match now.
        factory = make_factory(mock_chunker_classes)

        for extension in (".", ".m", "m", ".mkd"):
            assert factory.get_chunker(extension) is factory._default_chunker

        mock_chunker_classes["structure"].assert_not_called()

    def test_txt_uses_sentence_based_chunker(self, mock_chunker_classes):
        factory = make_factory(mock_chunker_classes)

        factory.get_chunker(".txt")

        mock_chunker_classes["sentence"].assert_called_once()
        mock_chunker_classes["structure"].assert_not_called()

    def test_pdf_uses_sentence_based_chunker(self, mock_chunker_classes):
        factory = make_factory(mock_chunker_classes)

        factory.get_chunker(".pdf")

        mock_chunker_classes["sentence"].assert_called_once()

    def test_html_uses_sentence_based_chunker(self, mock_chunker_classes):
        factory = make_factory(mock_chunker_classes)

        factory.get_chunker(".html")

        mock_chunker_classes["sentence"].assert_called_once()

    def test_dot_text_extension_routes_to_sentence_based_not_structure_aware(
        self, mock_chunker_classes
    ):
        # Regression test: ".text" used to also appear in the markdown
        # extension set, which meant it was silently routed to
        # StructureAwareChunker instead of SentenceBasedChunker.
        factory = make_factory(mock_chunker_classes)

        factory.get_chunker(".text")

        mock_chunker_classes["sentence"].assert_called_once()
        mock_chunker_classes["structure"].assert_not_called()

    def test_unknown_extension_returns_default_chunker(self, mock_chunker_classes):
        factory = make_factory(mock_chunker_classes)

        result = factory.get_chunker(".xyz")

        mock_chunker_classes["code"].assert_not_called()
        mock_chunker_classes["structure"].assert_not_called()
        mock_chunker_classes["sentence"].assert_not_called()
        assert result is factory._default_chunker


# ---------------------------------------------------------------------------
# Instance reuse / caching
# ---------------------------------------------------------------------------


class TestCaching:

    def test_same_extension_returns_cached_instance_not_rebuilt(
        self, mock_chunker_classes
    ):
        factory = make_factory(mock_chunker_classes)

        first = factory.get_chunker(".py")
        second = factory.get_chunker(".py")

        assert first is second
        mock_chunker_classes["code"].assert_called_once()

    def test_markdown_extension_returns_cached_instance_not_rebuilt(
        self, mock_chunker_classes
    ):
        factory = make_factory(mock_chunker_classes)

        first = factory.get_chunker(".md")
        second = factory.get_chunker(".md")

        assert first is second
        mock_chunker_classes["structure"].assert_called_once()

    def test_different_unknown_extensions_share_the_default_instance(
        self, mock_chunker_classes
    ):
        factory = make_factory(mock_chunker_classes)

        first = factory.get_chunker(".xyz")
        second = factory.get_chunker(".abc")

        assert first is second


# ---------------------------------------------------------------------------
# Extension normalization
# ---------------------------------------------------------------------------


class TestNormalization:

    def test_extension_without_leading_dot_is_normalized(self, mock_chunker_classes):
        factory = make_factory(mock_chunker_classes)

        factory.get_chunker("py")

        config = mock_chunker_classes["code"].call_args.args[0]
        assert config.language == "python"

    def test_extension_with_whitespace_and_mixed_case_is_normalized(
        self, mock_chunker_classes
    ):
        factory = make_factory(mock_chunker_classes)

        factory.get_chunker("  .MD  ")

        mock_chunker_classes["structure"].assert_called_once()

    def test_normalization_makes_different_input_forms_hit_the_same_cache(
        self, mock_chunker_classes
    ):
        factory = make_factory(mock_chunker_classes)

        first = factory.get_chunker("PY")
        second = factory.get_chunker(".py")

        assert first is second
        mock_chunker_classes["code"].assert_called_once()

    def test_empty_extension_returns_default_chunker(self, mock_chunker_classes):
        factory = make_factory(mock_chunker_classes)

        result = factory.get_chunker("")

        assert result is factory._default_chunker


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestConfigValidation:

    def test_chunk_size_below_minimum_is_rejected(self):
        with pytest.raises(ValidationError):
            ChunkerBuildConfig(chunk_size=399)

    def test_chunk_size_at_maximum_is_rejected(self):
        with pytest.raises(ValidationError):
            ChunkerBuildConfig(chunk_size=2000)

    def test_code_max_lines_per_chunk_zero_is_rejected(self):
        with pytest.raises(ValidationError):
            ChunkerBuildConfig(code_max_lines_per_chunk=0)

    def test_overlap_not_smaller_than_chunk_size_is_rejected(self):
        with pytest.raises(ValidationError):
            ChunkerBuildConfig(chunk_size=400, chunk_overlap=450)

    def test_overlap_equal_to_chunk_size_is_rejected(self):
        with pytest.raises(ValidationError):
            ChunkerBuildConfig(chunk_size=400, chunk_overlap=400)
