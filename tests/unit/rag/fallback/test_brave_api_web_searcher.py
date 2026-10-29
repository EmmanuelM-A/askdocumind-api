"""
Unit tests for BraveAPIWebSearcher.

No test uses the network. A fake replaces requests.get and routes each URL to
a canned response, a fake replaces DDGS, and the URL safety check is patched
where a test is about something else. The safety check has its own tests, with
a fake DNS resolver.

The searcher handles failures by falling back and returning less content, so
it raises nothing the tests could check by status code. The tests check the
fallback result instead.
"""

import asyncio
import socket
from types import SimpleNamespace
from typing import ClassVar

import pytest
import requests
from pydantic import SecretStr

from src.rag.services.fallback import brave_api_web_searcher as module
from src.rag.services.fallback.brave_api_web_searcher import (
    BraveAPIWebSearcher,
    _decode,
    _is_public_ip,
    _SearchResult,
)

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

# ---------------------------------------------------------------------------
# Fakes and helpers
# ---------------------------------------------------------------------------


class FakeResponse:
    """Stands in for a streamed requests.Response."""

    def __init__(self, status=200, headers=None, body=b"", json_data=None):
        self.status_code = status
        self.headers = {"Content-Type": "text/html; charset=utf-8", **(headers or {})}
        self._body = body
        self._json = json_data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json

    def iter_content(self, chunk_size=1):
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]


class FakeWeb:
    """Replaces requests.get. Routes by URL and records every call."""

    def __init__(self):
        self.routes = {}
        self.calls = []

    def add(self, url, outcome):
        self.routes[url] = outcome

    def __call__(self, *args, **kwargs):
        url = kwargs.get("url") or args[0]
        self.calls.append((url, kwargs))

        if url not in self.routes:
            raise AssertionError(f"Unexpected request to {url}")

        outcome = self.routes[url]

        if isinstance(outcome, BaseException):
            raise outcome

        return outcome

    @property
    def urls(self):
        return [url for url, _ in self.calls]


def brave_response(items):
    return FakeResponse(
        headers={"Content-Type": "application/json"},
        json_data={"web": {"results": items}},
    )


def make_ddgs(results=None, error=None):
    """Build a fake DDGS class. Its calls land in the class attribute calls."""

    class FakeDDGS:
        calls: ClassVar[list] = []

        def text(self, query, max_results):
            FakeDDGS.calls.append((query, max_results))

            if error:
                raise error

            return results or []

    return FakeDDGS


def result(url="https://a.example/p", title="Title", snippet="Snippet"):
    return _SearchResult(title=title, url=url, snippet=snippet)


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch):
    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(
            web=SimpleNamespace(
                BRAVE_API_KEY=SecretStr("test-key"),
                REQUEST_TIMEOUT_SECS=2,
                USER_AGENT="test-agent",
            )
        ),
    )
    monkeypatch.setattr(module, "_NUM_RESULTS", 3)


@pytest.fixture
def web(monkeypatch):
    fake = FakeWeb()
    monkeypatch.setattr(module.requests, "get", fake)
    return fake


@pytest.fixture
def searcher():
    return BraveAPIWebSearcher()


@pytest.fixture
def safe_urls(monkeypatch):
    """Treat every URL as safe, except those with 'unsafe' in them."""
    checked = []

    async def fake_is_url_safe(url):
        checked.append(url)
        return "unsafe" not in url

    monkeypatch.setattr(
        BraveAPIWebSearcher, "_is_url_safe", staticmethod(fake_is_url_safe)
    )
    return checked


# ---------------------------------------------------------------------------
# Finding search results
# ---------------------------------------------------------------------------


class TestSearching:

    @pytest.mark.asyncio
    async def test_brave_results_are_parsed_and_cleaned(self, searcher, web):
        web.add(
            BRAVE_URL,
            brave_response(
                [
                    {
                        "title": "A <strong>big</strong> &amp; bold",
                        "url": " https://a.example/x ",
                        "description": "Desc <strong>one</strong>",
                    },
                    {"title": None, "url": "https://b.example", "description": None},
                    "not-a-dict",
                ]
            ),
        )

        results = await searcher._search_for_results_on_the_web_for("query")

        assert [(r.title, r.url, r.snippet) for r in results] == [
            ("A big & bold", "https://a.example/x", "Desc one"),
            ("", "https://b.example", ""),
        ]

    @pytest.mark.asyncio
    async def test_the_query_is_normalised_and_sent_with_the_key(self, searcher, web):
        web.add(BRAVE_URL, brave_response([]))
        module.DDGS = make_ddgs()

        await searcher._search_for_results_on_the_web_for(
            "  what   is\nrag? " + "z" * 600
        )
        _, kwargs = web.calls[0]

        assert kwargs["params"]["q"].startswith("what is rag? zzz")
        assert len(kwargs["params"]["q"]) == 400
        assert kwargs["params"]["count"] == 3
        assert kwargs["headers"]["X-Subscription-Token"] == "test-key"
        assert kwargs["timeout"] == 2

        # A blank query makes no request at all.
        assert await searcher._search_for_results_on_the_web_for("  \n ") == []
        assert len(web.calls) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "brave_outcome",
        [
            requests.ConnectionError("brave is down"),
            FakeResponse(status=429, headers={"Content-Type": "application/json"}),
            brave_response([]),
        ],
        ids=["connection-error", "http-429", "no-results"],
    )
    async def test_brave_failure_or_no_results_falls_back_to_duckduckgo(
        self, searcher, web, monkeypatch, brave_outcome
    ):
        web.add(BRAVE_URL, brave_outcome)
        fake_ddgs = make_ddgs(
            [{"title": "DDG title", "href": "https://d.example/p", "body": "DDG body"}]
        )
        monkeypatch.setattr(module, "DDGS", fake_ddgs)

        results = await searcher._search_for_results_on_the_web_for("query")

        assert [(r.title, r.url, r.snippet) for r in results] == [
            ("DDG title", "https://d.example/p", "DDG body")
        ]
        assert fake_ddgs.calls == [("query", 3)]

    @pytest.mark.asyncio
    async def test_when_both_sources_fail_the_result_is_empty(
        self, searcher, web, monkeypatch
    ):
        web.add(BRAVE_URL, requests.ConnectionError("down"))
        monkeypatch.setattr(module, "DDGS", make_ddgs(error=RuntimeError("blocked")))

        assert await searcher.search_web("query") == []
        assert [page async for page in searcher.search_web_stream("query")] == []


# ---------------------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------------------


class TestUrlSafety:

    def test_only_public_addresses_are_accepted(self):
        public = ["8.8.8.8", "93.184.216.34", "2606:4700::1111"]
        blocked = [
            "127.0.0.1",
            "10.0.0.1",
            "172.16.5.4",
            "192.168.1.1",
            "169.254.169.254",
            "100.100.100.200",  # shared address space with a cloud metadata IP
            "224.0.0.1",
            "0.0.0.0",
            "::1",
            "fe80::1",
            "fc00::1",
            "::ffff:127.0.0.1",
            "::ffff:10.0.0.1",
        ]
        import ipaddress

        assert all(_is_public_ip(ipaddress.ip_address(a)) for a in public)
        assert not any(_is_public_ip(ipaddress.ip_address(a)) for a in blocked)

    @pytest.mark.asyncio
    async def test_bad_schemes_and_malformed_urls_are_unsafe(self):
        for url in (
            "ftp://example.com/file",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "http://",
            "http://[::1",
            "not a url",
            "",
        ):
            assert await BraveAPIWebSearcher._is_url_safe(url) is False, url

    @pytest.mark.asyncio
    async def test_the_resolved_addresses_decide_whether_a_url_is_safe(
        self, monkeypatch
    ):
        loop = asyncio.get_running_loop()

        def resolver(*addresses, error=None, delay=0):
            async def fake_getaddrinfo(host, port, **kwargs):
                await asyncio.sleep(delay)
                if error:
                    raise error
                return [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))
                    for address in addresses
                ]

            monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)

        check = BraveAPIWebSearcher._is_url_safe
        url = "https://example.com/page"

        resolver("93.184.216.34")
        assert await check(url) is True

        resolver("10.0.0.5")
        assert await check(url) is False

        resolver("93.184.216.34", "127.0.0.1")  # one private address is enough
        assert await check(url) is False

        resolver()
        assert await check(url) is False

        resolver(error=socket.gaierror("no such host"))
        assert await check(url) is False

        resolver("93.184.216.34", delay=5)  # the lookup times out
        monkeypatch.setattr(
            module.settings.web, "REQUEST_TIMEOUT_SECS", 0.05, raising=False
        )
        assert await check(url) is False


# ---------------------------------------------------------------------------
# Fetching one page
# ---------------------------------------------------------------------------


class TestFetching:

    @pytest.mark.asyncio
    async def test_a_safe_page_is_returned_as_html(self, searcher, web, safe_urls):
        html = "<html><body>Hello</body></html>"
        web.add("https://a.example/p", FakeResponse(body=html.encode()))

        content = await searcher._fetch_web_content(result())

        _, kwargs = web.calls[0]
        assert content == html
        assert kwargs["allow_redirects"] is False
        assert kwargs["stream"] is True
        assert kwargs["headers"] == {"User-Agent": "test-agent"}
        assert kwargs["timeout"] == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "outcome",
        [
            FakeResponse(status=404, body=b"not found"),
            FakeResponse(headers={"Content-Type": "application/pdf"}, body=b"%PDF"),
            requests.ConnectionError("refused"),
            FakeResponse(body=b""),
        ],
        ids=["http-404", "not-html", "connection-error", "empty-body"],
    )
    async def test_an_unusable_page_falls_back_to_the_title_and_snippet(
        self, searcher, web, safe_urls, outcome
    ):
        web.add("https://a.example/p", outcome)

        content = await searcher._fetch_web_content(
            result(title="Title & Co", snippet="A <snip>")
        )

        assert content == (
            "<html><body><h1>Title &amp; Co</h1><p>A &lt;snip&gt;</p></body></html>"
        )

    @pytest.mark.asyncio
    async def test_an_unsafe_url_is_never_requested(self, searcher, web, safe_urls):
        unsafe = result(url="https://unsafe.example/p", title="T", snippet="S")
        nothing = result(url="https://unsafe.example/p", title="", snippet="")

        assert "<h1>T</h1><p>S</p>" in await searcher._fetch_web_content(unsafe)
        assert await searcher._fetch_web_content(nothing) == ""
        assert web.calls == []

    @pytest.mark.asyncio
    async def test_redirects_are_followed_and_every_target_is_checked(
        self, searcher, web, safe_urls
    ):
        web.add(
            "https://a.example/start",
            FakeResponse(status=302, headers={"Location": "/next"}),
        )
        web.add(
            "https://a.example/next",
            FakeResponse(status=301, headers={"Location": "https://b.example/final"}),
        )
        web.add("https://b.example/final", FakeResponse(body=b"<p>final page</p>"))

        content = await searcher._fetch_web_content(
            result(url="https://a.example/start")
        )

        assert content == "<p>final page</p>"
        assert web.urls == [
            "https://a.example/start",
            "https://a.example/next",
            "https://b.example/final",
        ]
        assert safe_urls == web.urls
        assert all(kwargs["allow_redirects"] is False for _, kwargs in web.calls)

    @pytest.mark.asyncio
    async def test_a_redirect_that_cannot_be_followed_falls_back(
        self, searcher, web, safe_urls
    ):
        backup = "<html><body><h1>Title</h1><p>Snippet</p></body></html>"

        # A redirect to an unsafe address is never requested.
        web.add(
            "https://a.example/start",
            FakeResponse(status=302, headers={"Location": "https://unsafe.example/x"}),
        )
        assert (
            await searcher._fetch_web_content(result("https://a.example/start"))
            == backup
        )
        assert web.urls == ["https://a.example/start"]

        # A redirect loop stops after the limit.
        web.calls.clear()
        web.add(
            "https://a.example/loop",
            FakeResponse(status=302, headers={"Location": "https://a.example/loop"}),
        )
        assert (
            await searcher._fetch_web_content(result("https://a.example/loop"))
            == backup
        )
        assert len(web.calls) == module._MAX_REDIRECTS + 1

    @pytest.mark.asyncio
    async def test_a_page_over_the_size_limit_is_cut(
        self, searcher, web, safe_urls, monkeypatch
    ):
        monkeypatch.setattr(module, "_MAX_PAGE_BYTES", 100)
        web.add("https://a.example/p", FakeResponse(body=b"<p>" + b"x" * 1000))

        content = await searcher._fetch_web_content(result())

        assert len(content) == 100
        assert content.startswith("<p>xxx")

    def test_pages_are_decoded_by_header_then_utf8_then_a_guess(self):
        text = "café Zürich"

        assert (
            _decode(text.encode("iso-8859-1"), "text/html; charset=ISO-8859-1") == text
        )
        assert _decode(text.encode("utf-8"), "text/html") == text
        assert _decode(text.encode("utf-8"), "text/html; charset=bogus-9") == text
        assert isinstance(_decode(b"\xff\xfe\x00 bad bytes", ""), str)


# ---------------------------------------------------------------------------
# Fetching all results
# ---------------------------------------------------------------------------


class TestSearchFlow:

    @pytest.mark.asyncio
    async def test_contents_keep_result_order_and_empty_ones_are_skipped(
        self, searcher, monkeypatch
    ):
        results = [
            result("https://a.example/1"),
            result("https://a.example/2"),
            result("https://a.example/3"),
        ]

        async def fake_search(query):
            return results

        async def fake_fetch(item):
            # The first page is the slowest, yet it must still come first.
            await asyncio.sleep({"1": 0.05, "2": 0, "3": 0.01}[item.url[-1]])
            return {"1": "one", "2": "", "3": "three"}[item.url[-1]]

        monkeypatch.setattr(searcher, "_search_for_results_on_the_web_for", fake_search)
        monkeypatch.setattr(searcher, "_fetch_web_content", fake_fetch)

        assert [r.content for r in await searcher.search_web("query")] == [
            "one",
            "three",
        ]
        assert [page.content async for page in searcher.search_web_stream("query")] == [
            "one",
            "three",
        ]
        assert [r.url for r in await searcher.search_web("query")] == [
            "https://a.example/1",
            "https://a.example/3",
        ]

    @pytest.mark.asyncio
    async def test_pages_download_in_parallel_up_to_the_limit(
        self, searcher, monkeypatch
    ):
        results = [result(f"https://a.example/{i}") for i in range(8)]
        active = 0
        peak = 0

        async def fake_search(query):
            return results

        async def fake_fetch(item):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.02)
            active -= 1
            return item.url

        monkeypatch.setattr(searcher, "_search_for_results_on_the_web_for", fake_search)
        monkeypatch.setattr(searcher, "_fetch_web_content", fake_fetch)

        contents = await searcher.search_web("query")

        assert len(contents) == 8
        assert 1 < peak <= module._MAX_PARALLEL_FETCHES

    @pytest.mark.asyncio
    async def test_closing_the_stream_early_cancels_unfinished_downloads(
        self, searcher, monkeypatch
    ):
        results = [result(f"https://a.example/{i}") for i in range(3)]
        cancelled = []

        async def fake_search(query):
            return results

        async def fake_fetch(item):
            if item.url.endswith("/0"):
                return "first"
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(item.url)
                raise
            return "late"

        monkeypatch.setattr(searcher, "_search_for_results_on_the_web_for", fake_search)
        monkeypatch.setattr(searcher, "_fetch_web_content", fake_fetch)

        stream = searcher.search_web_stream("query")
        assert (await stream.__anext__()).content == "first"
        await stream.aclose()

        assert sorted(cancelled) == ["https://a.example/1", "https://a.example/2"]
