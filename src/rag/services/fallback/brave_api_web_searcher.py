"""
This module defines the BraveApiWebSearcher class, which implements the
WebSearcher interface to perform web searches using the Brave Search API.
"""

import asyncio
import ipaddress
import logging
from dataclasses import dataclass
import socket
from html import escape
from typing import AsyncIterable
from urllib.parse import urlparse

import requests
from ddgs import DDGS
from ddgs.exceptions import DDGSException
from requests import HTTPError

from src.config.configs import settings
from src.exceptions import server_error
from src.rag.services.chunk.chunker import Chunker
from src.rag.services.embed.embedder import Embedder
from src.rag.services.fallback.web_searcher import WebSearcher


@dataclass
class _SearchResult:
    title: str
    url: str
    snippet: str


_BATCH_SIZE = settings.rag.PROCESSING_BATCH_SIZE
_NUM_RESULTS = settings.rag.MAX_SEARCH_RESULTS

_logger = logging.getLogger(__name__)


class BraveAPIWebSearcher(WebSearcher):
    def __init__(self, chunker: Chunker, embedder: Embedder) -> None:
        self._chunker = chunker
        self._embedder = embedder
        self._URL = "https://api.search.brave.com/res/v1/web/search"
        self._HEADERS = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": settings.web.BRAVE_API_KEY.get_secret_value(),
        }

    async def search_web(self, query: str) -> list[str]:
        """
        Performs a web search using the Brave Search API and returns the content
        of the search results as a list of strings.
        """
        search_results = self._search_for_results_on_the_web_for(query)

        contents: list[str] = []
        successes = 0

        for i, result in enumerate(search_results):
            url = result.url.strip()

            if not url or not await self._is_url_safe(url):
                _logger.debug(f"Skipping unsafe or empty URL: '{url}'")
                continue

            content = await self._fetch_web_content(result)

            if not content:
                _logger.debug(f"No content fetched for URL: '{url}'")
                continue

            contents.append(content)
            successes += 1

        if successes == 0:
            return []

        _logger.debug(
            f"Successfully fetched content from "
            f"{successes}/{len(search_results)} search results"
        )

        return contents

    async def search_web_stream(self, query: str) -> AsyncIterable[str]:
        """
        Performs a web search using the Brave Search API and yields the content
        of the search results as an asynchronous iterator of strings.
        """
        search_results = self._search_for_results_on_the_web_for(query)

        for i, result in enumerate(search_results):
            url = result.url.strip()

            if not url or not await self._is_url_safe(url):
                _logger.debug(f"Skipping unsafe or empty URL: '{url}'")
                continue

            content = await self._fetch_web_content(result)

            if not content:
                _logger.debug(f"No content fetched for URL: '{url}'")
                continue

            _logger.debug(
                f"Yielding content for URL: '{url}'"
                f" Search result {i + 1}/{len(search_results)}"
            )

            yield content

    # ========================== HELPER METHODS ==========================

    def _search_for_results_on_the_web_for(self, query: str) -> list[_SearchResult]:
        """
        Performs a web search using the Brave Search API and yields the content
        of the search results.

        If the Brave Search API fails or returns no results, it falls back to
        using DuckDuckGo's search API.
        """
        search_results: list[_SearchResult] = []

        try:
            response = requests.get(
                url=self._URL,
                headers=self._HEADERS,
                params={"q": query, "count": _NUM_RESULTS},
                timeout=settings.web.REQUEST_TIMEOUT_SECS,
            )
            response.raise_for_status()

            data = response.json()
            items = data.get("web", {}).get("results", [])

            if not items:
                search_results = self._fallback_search(query, num_results=_NUM_RESULTS)
            else:
                for item in items:
                    search_results.append(
                        _SearchResult(
                            title=item.get("title", ""),
                            url=item.get("url", ""),
                            snippet=item.get("description", ""),
                        )
                    )
        except HTTPError | Exception as e:
            _logger.exception(
                "Failed to fetch search results from Brave Search API", exc_info=e
            )
            search_results = self._fallback_search(query, num_results=_NUM_RESULTS)

        if not search_results:
            raise server_error(
                message=f"No search results found for query '{query}'",
                error_code="NO_SEARCH_RESULTS",
            )

        return search_results

    @staticmethod
    def _fallback_search(query: str, num_results: int = 5) -> list[_SearchResult]:
        """
        Fallback search method using DuckDuckGo's search API.
        """
        try:
            raw_results = DDGS().text(query, max_results=num_results)

            _logger.debug(f"Retrieved {len(raw_results)} results from fallback search")

            return [
                _SearchResult(
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    snippet=result.get("body", ""),
                )
                for result in raw_results
            ]
        except DDGSException | Exception:
            return []

    async def _is_url_safe(self, url: str) -> bool:
        """
        Checks if the given URL is safe to access by resolving its hostname
        and ensuring it does not point to any private or reserved IP addresses.
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False
        try:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(
                hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM
            )
            for _, _, _, _, sockaddr in infos:
                addr = sockaddr[0]
                ip = ipaddress.ip_address(addr)
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_reserved
                    or ip.is_multicast
                ):
                    _logger.debug(f"Blocked unsafe IP {addr} for host {hostname}")
                    return False
            return True
        except Exception as e:
            _logger.debug(f"Error resolving {hostname}: {e}")
            return False

    @staticmethod
    def _backup_web_content(result: _SearchResult) -> str:
        """
        Fallback method to generate HTML content from the search result's
        title and snippet.
        """
        return (
            "<html><body>"
            f"<h1>{escape(result.title)}</h1>"
            f"<p>{escape(result.snippet)}</p>"
            "</body></html>"
        )

    async def _fetch_web_content(self, result: _SearchResult) -> str:
        """
        Fetches the web content from the given search result's URL.
        If the URL is deemed unsafe or if fetching fails, it falls back to
        generating HTML content from the search result's title and snippet.
        """

        if not await self._is_url_safe(result.url):
            return self._backup_web_content(result)

        headers = {"User-Agent": settings.web.USER_AGENT}

        try:
            response = requests.get(
                url=result.url,
                headers=headers,
                timeout=settings.web.REQUEST_TIMEOUT_SECS,
            )

            response.raise_for_status()
        except HTTPError as e:
            raise server_error(
                message=f"Failed to fetch web content from '{result.url}'",
                error_code="FETCH_ERROR",
            ) from e

        content_type = response.headers.get("Content-Type")

        if content_type and "text/html" not in content_type:
            _logger.debug(f"Non-HTML content type '{content_type}' for '{result.url}'")
            return self._backup_web_content(result)

        if not response.text:
            return self._backup_web_content(result)

        return response.text
