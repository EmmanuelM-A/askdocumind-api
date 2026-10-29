"""
Unit tests for ExtractorFactory.

The factory builds its extension table from settings when the module is
imported, so tests that change the configured code extensions reload the
module with patched settings. A fixture reloads it again afterward.

Error tests assert only the HTTP status code of the raised ApiException.
"""

import importlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.config import configs
from src.exceptions.base import ApiException
from src.rag.services.extract.extractors import factory as factory_module
from src.rag.services.extract.extractors.docx_extractor import DocxExtractor
from src.rag.services.extract.extractors.html_extractor import HtmlExtractor
from src.rag.services.extract.extractors.pdf_extractor import PdfExtractor
from src.rag.services.extract.extractors.plain_text_extractor import (
    PlainTextExtractor,
)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def load_factory():
    """Reload the factory module with the given configured code extensions."""

    def _load(extensions):
        fake = SimpleNamespace(
            uploads=SimpleNamespace(ALLOWED_CODE_EXTENSIONS=extensions)
        )
        with patch.object(configs, "settings", fake):
            return importlib.reload(factory_module)

    yield _load

    importlib.reload(factory_module)


# ---------------------------------------------------------------------------
# Selecting an extractor
# ---------------------------------------------------------------------------


class TestSelection:

    def test_built_in_extensions_map_to_their_extractors(self, load_factory):
        factory = load_factory([]).ExtractorFactory

        assert isinstance(factory.get_extractor(".pdf"), PdfExtractor)
        assert isinstance(factory.get_extractor(".docx"), DocxExtractor)
        assert isinstance(factory.get_extractor(".html"), HtmlExtractor)
        assert isinstance(factory.get_extractor(".txt"), PlainTextExtractor)
        assert isinstance(factory.get_extractor(".md"), PlainTextExtractor)

    def test_configured_code_extensions_use_the_plain_text_extractor(
        self, load_factory
    ):
        factory = load_factory([".py", ".go"]).ExtractorFactory

        assert isinstance(factory.get_extractor(".py"), PlainTextExtractor)
        assert isinstance(factory.get_extractor(".go"), PlainTextExtractor)

    def test_lookup_ignores_case_and_surrounding_whitespace(self, load_factory):
        factory = load_factory([]).ExtractorFactory

        assert isinstance(factory.get_extractor(".PDF"), PdfExtractor)
        assert isinstance(factory.get_extractor("  .Docx\n"), DocxExtractor)

    def test_each_call_returns_a_new_instance(self, load_factory):
        factory = load_factory([]).ExtractorFactory

        assert factory.get_extractor(".pdf") is not factory.get_extractor(".pdf")


# ---------------------------------------------------------------------------
# Configured extensions
# ---------------------------------------------------------------------------


class TestConfiguredExtensions:

    def test_configured_entries_are_lowercased_and_given_a_leading_dot(
        self, load_factory
    ):
        factory = load_factory([".JS", "go", " Rs "]).ExtractorFactory

        for extension in (".js", ".go", ".rs"):
            assert isinstance(factory.get_extractor(extension), PlainTextExtractor)

    def test_blank_configured_entries_are_ignored(self, load_factory):
        module = load_factory(["", "   "])

        assert "." not in module._EXTRACTORS
        assert "" not in module._EXTRACTORS

    def test_a_configured_extension_cannot_replace_a_built_in_extractor(
        self, load_factory
    ):
        factory = load_factory([".pdf", ".html"]).ExtractorFactory

        assert isinstance(factory.get_extractor(".pdf"), PdfExtractor)
        assert isinstance(factory.get_extractor(".html"), HtmlExtractor)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    def test_extension_without_a_leading_dot_raises_422(self, load_factory):
        factory = load_factory([]).ExtractorFactory

        for extension in ("pdf", "", "   "):
            with pytest.raises(ApiException) as exc_info:
                factory.get_extractor(extension)

            assert exc_info.value.status_code == 422

    def test_unsupported_extension_raises_422(self, load_factory):
        factory = load_factory([".py"]).ExtractorFactory

        for extension in (".exe", ".htm", ".", ".pdf.bak"):
            with pytest.raises(ApiException) as exc_info:
                factory.get_extractor(extension)

            assert exc_info.value.status_code == 422
