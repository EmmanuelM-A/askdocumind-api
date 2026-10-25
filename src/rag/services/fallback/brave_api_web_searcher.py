"""
This module defines the BraveAPIWebSearcher class, which implements the
WebSearcher interface to perform web searches using the Brave Search API.
"""

import asyncio
import ipaddress
import logging
import re
import socket
import time
from collections.abc import AsyncIterable
from dataclasses import dataclass
from html import escape, unescape
from urllib.parse import urljoin, urlparse

import requests
from charset_normalizer import from_bytes
from ddgs import DDGS

from src.config.configs import settings
from src.rag.schemas.retrieval import WebResult
from src.rag.services.extract.extractors.html_extractor import html_to_text
from src.rag.services.fallback.web_searcher import WebSearcher


@dataclass
class _SearchResult:
    title: str
    url: str
    snippet: str


@dataclass
class _Page:
    """The outcome of one request: a redirect target, the page text, or neither."""

    redirect_to: str | None = None
    text: str | None = None


_NUM_RESULTS = settings.web.MAX_SEARCH_RESULTS
_MAX_RESULT_CHARS = settings.web.MAX_WEB_RESULT_CHARS

# Brave rejects queries longer than 400 characters.
_MAX_QUERY_CHARS = 400
_MAX_PAGE_BYTES = 2 * 1024 * 1024
_MAX_REDIRECTS = 3
_MAX_PARALLEL_FETCHES = 5
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
_TAG_PATTERN = re.compile(r"<[^>]+>")
_CHARSET_PATTERN = re.compile(r"charset=([^;\s]+)", re.IGNORECASE)

_logger = logging.getLogger(__name__)


def _clean_text(value: str | None) -> str:
    """Remove the highlight tags Brave adds to titles and descriptions."""
    return " ".join(unescape(_TAG_PATTERN.sub("", value or "")).split())


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    True only for addresses on the public internet. The check is_private
    alone misses shared address space (100.64.0.0/10, which includes a cloud
    metadata address) and IPv4 addresses wrapped in IPv6.
    """
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    return ip.is_global and not (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _decode(body: bytes, content_type: str) -> str:
    """
    Decode a page. A charset in the header wins, then UTF-8, then a guess.
    The requests library would read a page without a charset as Latin-1,
    which garbles UTF-8 text.
    """
    declared = _CHARSET_PATTERN.search(content_type)

    for encoding in (declared.group(1).strip("\"'") if declared else None, "utf-8"):
        if encoding:
            try:
                return body.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue

    match = from_bytes(body).best()
    return str(match) if match else body.decode("utf-8", errors="replace")


class BraveAPIWebSearcher(WebSearcher):
    def __init__(self) -> None:
        self._URL = "https://api.search.brave.com/res/v1/web/search"
        self._HEADERS = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": settings.web.BRAVE_API_KEY.get_secret_value(),
        }

    async def search_web(self, query: str) -> list[WebResult]:
        """
        Performs a web search using the Brave Search API and returns the text
        of the search results with their URL and title, in result order.
        """
        results = await self._search_for_results_on_the_web_for(query)

        if not results:
            return []

        semaphore = asyncio.Semaphore(_MAX_PARALLEL_FETCHES)
        pages = await asyncio.gather(
            *(self._fetch_limited(result, semaphore) for result in results)
        )
        contents = [page for page in pages if page is not None]

        _logger.debug(
            "Fetched content for %d/%d search results", len(contents), len(results)
        )

        return contents

    async def search_web_stream(self, query: str) -> AsyncIterable[WebResult]:
        """
        Performs a web search using the Brave Search API and yields the content
        of the search results in result order. All pages download at the same
        time, so each one is ready by the time the caller asks for it.
        """
        results = await self._search_for_results_on_the_web_for(query)

        semaphore = asyncio.Semaphore(_MAX_PARALLEL_FETCHES)
        tasks = [
            asyncio.create_task(self._fetch_limited(result, semaphore))
            for result in results
        ]

        try:
            for index, task in enumerate(tasks):
                content = await task

                if content is None:
                    continue

                _logger.debug(
                    "Yielding content for search result %d/%d", index + 1, len(tasks)
                )

                yield content
        finally:
            # The caller can stop early, so stop the downloads still running.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # ========================== HELPER METHODS ==========================

    async def _search_for_results_on_the_web_for(
        self, query: str
    ) -> list[_SearchResult]:
        """
        Performs a web search using the Brave Search API and returns the
        results. If the Brave Search API fails or returns no results, it falls
        back to DuckDuckGo. A query with no results gives an empty list.
        """
        query = " ".join(query.split())[:_MAX_QUERY_CHARS]

        if not query:
            return []

        results = await self._brave_search(query)

        if not results:
            results = await self._fallback_search(query, num_results=_NUM_RESULTS)

        if not results:
            _logger.warning("No search results found for the query.")

        return results

    async def _brave_search(self, query: str) -> list[_SearchResult]:
        try:
            response = await asyncio.to_thread(
                requests.get,
                url=self._URL,
                headers=self._HEADERS,
                params={"q": query, "count": _NUM_RESULTS},
                timeout=settings.web.REQUEST_TIMEOUT_SECS,
            )
            response.raise_for_status()
            items = response.json().get("web", {}).get("results", [])
        except Exception:
            _logger.exception("Failed to fetch search results from Brave Search API")
            return []

        return [
            _SearchResult(
                title=_clean_text(item.get("title")),
                url=(item.get("url") or "").strip(),
                snippet=_clean_text(item.get("description")),
            )
            for item in items
            if isinstance(item, dict)
        ]

    @staticmethod
    async def _fallback_search(query: str, num_results: int = 5) -> list[_SearchResult]:
        """
        Fallback search method using DuckDuckGo's search API.
        """
        try:
            raw_results = await asyncio.to_thread(
                lambda: DDGS().text(query, max_results=num_results)
            )
        except Exception:
            _logger.warning("Fallback search failed", exc_info=True)
            return []

        _logger.debug("Retrieved %d results from fallback search", len(raw_results))

        return [
            _SearchResult(
                title=_clean_text(result.get("title")),
                # DuckDuckGo results name the link "href", not "url".
                url=(result.get("href") or result.get("url") or "").strip(),
                snippet=_clean_text(result.get("body")),
            )
            for result in raw_results
        ]

    @staticmethod
    async def _is_url_safe(url: str) -> bool:
        """
        Checks if the given URL is safe to access by resolving its hostname
        and ensuring it points only to public IP addresses.
        """
        try:
            parsed = urlparse(url)

            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return False

            infos = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(
                    parsed.hostname,
                    None,
                    family=socket.AF_UNSPEC,
                    type=socket.SOCK_STREAM,
                ),
                timeout=settings.web.REQUEST_TIMEOUT_SECS,
            )

            if not infos:
                return False

            for _, _, _, _, sockaddr in infos:
                # An IPv6 address can carry a scope such as "fe80::1%eth0".
                address = ipaddress.ip_address(str(sockaddr[0]).split("%")[0])

                if not _is_public_ip(address):
                    _logger.debug(
                        "Blocked non-public IP %s for host %s", address, parsed.hostname
                    )
                    return False

            return True
        except Exception as e:
            _logger.debug("Could not verify the URL '%s': %s", url, e)
            return False

    @staticmethod
    def _backup_web_content(result: _SearchResult) -> str:
        """
        Fallback method to generate HTML content from the search result's
        title and snippet. It returns an empty string when both are empty.
        """
        if not (result.title or result.snippet):
            return ""

        return (
            "<html><body>"
            f"<h1>{escape(result.title)}</h1>"
            f"<p>{escape(result.snippet)}</p>"
            "</body></html>"
        )

    async def _fetch_limited(
        self, result: _SearchResult, semaphore: asyncio.Semaphore
    ) -> WebResult | None:
        async with semaphore:
            html = await self._fetch_web_content(result)

        if not html:
            return None

        try:
            # Parsing a large page takes a while, so it runs off the event loop.
            text = await asyncio.to_thread(html_to_text, html)
        except Exception as e:
            _logger.debug("Could not read the text of '%s': %s", result.url, e)
            return None

        if not text:
            return None

        return WebResult(
            url=result.url,
            title=result.title,
            content=text[:_MAX_RESULT_CHARS],
        )

    async def _fetch_web_content(self, result: _SearchResult) -> str:
        """
        Fetches the web content from the given search result's URL. If the URL
        is unsafe or the page cannot be used (an error status, a timeout, a
        non-HTML type or too many redirects), it falls back to HTML built from
        the result's title and snippet. This method does not raise.
        """
        try:
            page = await self._download_page(result.url)
        except Exception as e:
            _logger.debug("Could not fetch '%s': %s", result.url, e)
            page = None

        return page or self._backup_web_content(result)

    async def _download_page(self, url: str) -> str | None:
        """
        Downloads a page and follows redirects by hand, so every address in
        the chain passes the safety check. A redirect to an internal address
        is blocked the same way as a search result that points there.
        """
        for _ in range(_MAX_REDIRECTS + 1):
            if not await self._is_url_safe(url):
                return None

            page = await asyncio.to_thread(self._get_once, url)

            if page.redirect_to:
                url = urljoin(url, page.redirect_to)
                continue

            return page.text

        return None

    @staticmethod
    def _get_once(url: str) -> _Page:
        """Make one request without following redirects. This blocks."""
        timeout = settings.web.REQUEST_TIMEOUT_SECS
        deadline = time.monotonic() + timeout * 3

        with requests.get(
            url,
            headers={"User-Agent": settings.web.USER_AGENT},
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code in _REDIRECT_STATUSES:
                return _Page(redirect_to=response.headers.get("Location"))

            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")

            if content_type and not any(
                html_type in content_type.lower() for html_type in _HTML_CONTENT_TYPES
            ):
                _logger.debug("Non-HTML content type '%s' for '%s'", content_type, url)
                return _Page()

            body = bytearray()

            # Read in blocks, so a huge or slow page cannot use unlimited
            # memory or time. A page cut at the limit still gives its start.
            for block in response.iter_content(chunk_size=64 * 1024):
                body += block

                if len(body) >= _MAX_PAGE_BYTES or time.monotonic() > deadline:
                    break

            return _Page(text=_decode(bytes(body[:_MAX_PAGE_BYTES]), content_type))
