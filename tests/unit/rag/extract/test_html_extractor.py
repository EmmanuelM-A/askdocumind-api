"""
Unit tests for HtmlExtractor.

Each test writes a small HTML file to tmp_path, so the extractor runs the
real BeautifulSoup and lxml parser.

Error tests assert only the HTTP status code of the raised ApiException.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.exceptions.base import ApiException
from src.rag.services.extract.extractors import html_extractor
from src.rag.services.extract.extractors.html_extractor import HtmlExtractor

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def segment_target():
    """A large target, so segments only close at headings unless a test says so."""
    fake = SimpleNamespace(rag=SimpleNamespace(SEGMENT_TARGET_CHARS=10_000))
    with patch("src.rag.services.extract.extractors.extractor.settings", fake):
        yield fake


def extract_texts(tmp_path, html: str | bytes) -> list[str]:
    path = tmp_path / "page.html"
    path.write_bytes(html if isinstance(html, bytes) else html.encode("utf-8"))
    return [s.text for s in HtmlExtractor().extract(path)]


# ---------------------------------------------------------------------------
# Blocks and headings
# ---------------------------------------------------------------------------


class TestBlocksAndHeadings:

    def test_paragraphs_are_joined_into_one_segment_with_default_fields(self, tmp_path):
        path = tmp_path / "page.html"
        path.write_text("<body><p>First.</p><p>Second.</p></body>")

        segments = list(HtmlExtractor().extract(path))

        assert len(segments) == 1
        assert segments[0].text == "First.\nSecond."
        assert segments[0].page is None
        assert segments[0].separator == "\n\n"

    def test_headings_get_markdown_prefixes_and_start_new_segments(self, tmp_path):
        html = "<body><h2>Section</h2><p>Body.</p>" "<h3>Sub</h3><p>Detail.</p></body>"

        assert extract_texts(tmp_path, html) == [
            "## Section\nBody.",
            "### Sub\nDetail.",
        ]

    def test_whitespace_is_collapsed_and_entities_are_decoded(self, tmp_path):
        html = "<body><p>  Tom &amp;\n   Jerry \t &lt;3  </p></body>"

        assert extract_texts(tmp_path, html) == ["Tom & Jerry <3"]

    def test_inline_tags_do_not_split_a_block(self, tmp_path):
        html = "<body><p>Hello <b>bold</b> and <a href='#'>linked</a> text.</p></body>"

        assert extract_texts(tmp_path, html) == ["Hello bold and linked text."]

    def test_pre_block_keeps_its_internal_line_breaks_and_indentation(self, tmp_path):
        html = "<body><p>a</p><pre>\n  line1\n    line2\n</pre><p>b</p></body>"

        assert extract_texts(tmp_path, html) == ["a\n  line1\n    line2\nb"]

    def test_table_cells_become_separate_lines(self, tmp_path):
        html = (
            "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"
        )

        assert extract_texts(tmp_path, html) == ["a\nb\nc\nd"]

    def test_segment_closes_once_it_reaches_the_target_size(
        self, tmp_path, segment_target
    ):
        segment_target.rag.SEGMENT_TARGET_CHARS = 20
        html = f"<body><p>{'a' * 15}</p><p>{'b' * 15}</p><p>{'c' * 15}</p></body>"

        assert extract_texts(tmp_path, html) == [
            "a" * 15 + "\n" + "b" * 15,
            "c" * 15,
        ]

    def test_empty_file_and_empty_body_yield_no_segments(self, tmp_path):
        assert extract_texts(tmp_path, "") == []
        assert extract_texts(tmp_path, "<html><body></body></html>") == []

    def test_non_ascii_text_is_preserved(self, tmp_path):
        assert extract_texts(tmp_path, "<body><p>Café 日本語 🙂</p></body>") == [
            "Café 日本語 🙂"
        ]

    def test_declared_charset_is_used_to_decode_the_bytes(self, tmp_path):
        html = '<html><head><meta charset="iso-8859-1"></head><body><p>café</p></body></html>'

        assert extract_texts(tmp_path, html.encode("latin-1")) == ["café"]


# ---------------------------------------------------------------------------
# Text that sits next to other blocks
# ---------------------------------------------------------------------------


class TestMixedContent:

    def test_text_of_a_list_item_is_kept_when_it_holds_a_nested_list(self, tmp_path):
        html = "<body><ul><li>Fruits<ul><li>Apple</li></ul></li></ul></body>"

        assert extract_texts(tmp_path, html) == ["Fruits\nApple"]

    def test_text_beside_a_child_block_is_kept(self, tmp_path):
        html = "<body><div>Intro text <p>para</p> trailing</div></body>"

        assert extract_texts(tmp_path, html) == ["Intro text\npara\ntrailing"]

    def test_loose_text_directly_in_the_body_is_kept(self, tmp_path):
        assert extract_texts(tmp_path, "<body>Loose <p>para</p></body>") == [
            "Loose\npara"
        ]

    def test_fragment_without_a_body_tag_is_read(self, tmp_path):
        assert extract_texts(tmp_path, "<p>One</p><p>Two</p>") == ["One\nTwo"]

    def test_deeply_nested_markup_does_not_hit_the_recursion_limit(self, tmp_path):
        html = "<body>" + "<div>" * 3000 + "<p>deep</p>" + "</div>" * 3000 + "</body>"

        assert extract_texts(tmp_path, html) == ["deep"]


# ---------------------------------------------------------------------------
# Title handling
# ---------------------------------------------------------------------------


class TestTitle:

    def test_title_becomes_a_level_one_heading_when_the_body_has_other_content(
        self, tmp_path
    ):
        html = (
            "<html><head><title>Site</title></head>"
            "<body><h2>Section</h2><p>x</p></body></html>"
        )

        assert extract_texts(tmp_path, html) == ["# Site", "## Section\nx"]

    def test_title_alone_is_still_extracted(self, tmp_path):
        html = "<html><head><title>Only</title></head><body></body></html>"

        assert extract_texts(tmp_path, html) == ["# Only"]

    def test_title_is_skipped_when_the_first_heading_says_the_same(self, tmp_path):
        html = (
            "<html><head><title>Guide</title></head>"
            "<body><h1>guide</h1><p>x</p></body></html>"
        )

        assert extract_texts(tmp_path, html) == ["# guide\nx"]

    def test_title_inside_an_svg_is_not_the_page_title(self, tmp_path):
        html = "<body><svg><title>Icon</title></svg><p>Real content</p></body>"

        assert extract_texts(tmp_path, html) == ["Real content"]


# ---------------------------------------------------------------------------
# Removed content
# ---------------------------------------------------------------------------


class TestRemovedContent:

    def test_scripts_styles_and_page_chrome_are_dropped(self, tmp_path):
        html = (
            "<html><head><style>.x{}</style><script>var a=1;</script></head><body>"
            "<nav>Menu</nav><aside>Side</aside><noscript>Enable JS</noscript>"
            "<template><p>Tpl</p></template><iframe>Frame</iframe>"
            "<p>Real text</p><footer>Footer</footer></body></html>"
        )

        assert extract_texts(tmp_path, html) == ["Real text"]

    def test_comments_are_dropped(self, tmp_path):
        assert extract_texts(tmp_path, "<body><!-- hidden --><p>shown</p></body>") == [
            "shown"
        ]

    def test_text_inside_a_form_is_kept_but_form_controls_are_dropped(self, tmp_path):
        html = (
            "<body><form><p>Whole page in a form</p>"
            "<button>Submit</button><select><option>Pick</option></select>"
            "<textarea>typed</textarea></form></body>"
        )

        assert extract_texts(tmp_path, html) == ["Whole page in a form"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    def test_missing_file_raises_422(self, tmp_path):
        with pytest.raises(ApiException) as exc_info:
            list(HtmlExtractor().extract(tmp_path / "missing.html"))

        assert exc_info.value.status_code == 422

    def test_directory_instead_of_a_file_raises_422(self, tmp_path):
        with pytest.raises(ApiException) as exc_info:
            list(HtmlExtractor().extract(tmp_path))

        assert exc_info.value.status_code == 422

    def test_parser_failure_raises_422(self, tmp_path):
        path = tmp_path / "page.html"
        path.write_text("<p>x</p>")

        with patch.object(html_extractor, "BeautifulSoup", side_effect=ValueError):
            with pytest.raises(ApiException) as exc_info:
                list(HtmlExtractor().extract(path))

        assert exc_info.value.status_code == 422
