"""
Web search module for retrieving raw content from the internet when no
relevant documents are found.
"""

import ipaddress
import socket
import time
from dataclasses import dataclass
from html import escape
from typing import List, Optional
from urllib.parse import urlparse

import requests
from ddgs import DDGS
from ddgs.exceptions import DDGSException

from src.config.configs import settings
from src.logger.base_logger import BaseLogger


@dataclass
class WebContent:
    content: str
    source: str


@dataclass
class WebSearchResult:
    title: str
    snippet: str
    url: str


class WebSearcher:
    """
    Handles web search and raw content retrieval only.
    """

    def __init__(self) -> None:
        """
        Initializes the WebSearcher instance.
        """

        self._logger = BaseLogger(__name__)

        self.brave_api_key = (
            settings.web.BRAVE_SEARCH_API_KEY.get_secret_value()
            if settings.web.BRAVE_SEARCH_API_KEY
            else None
        )

    # ======================== WEB SEARCH METHODS ========================

    def search_and_retrieve_web_content(self, query: str) -> List[WebContent]:
        """
        Search the web based on the `query` and return the any raw HTML content
        for each matching result.
        """

        if not query or not query.strip():
            self._logger.error("Empty query provided to web search")
            return []

        self._logger.debug(f"Starting web search for query: {query[:100]}")

        try:
            search_results = self._search_web(query)

            if not search_results or len(search_results) == 0:
                self._logger.info("No web search results found")
                return []

            documents: List[WebContent] = []
            successful_fetches = 0

            for i, result in enumerate(search_results):
                try:

                    url = result.url.strip()
                    if not url or not url.startswith(("http://", "https://")):
                        self._logger.warning(f"Invalid URL in search result: {url}")
                        continue

                    # Respect rate limiting
                    if i > 0:
                        time.sleep(settings.web.WEB_REQUEST_DELAY_SECS)

                    document_content = self._fetch_content(result)
                    if document_content:
                        documents.append(
                            WebContent(
                                content=document_content,
                                source=url,
                            )
                        )
                        successful_fetches += 1

                except Exception as e:
                    self._logger.error(f"Error processing search result {i}: {e}")
                    continue

            self._logger.info(
                f"Web search completed: {successful_fetches}/{len(search_results)} successful"
            )
            return documents

        except Exception as e:
            self._logger.error(f"Critical error in web search: {e}", exc_info=True)
            return []

    # ========================== HELPER METHODS ==========================

    def _search_web(self, query: str) -> List[WebSearchResult]:
        """
        Perform web search using Brave Search API.

        Returns:
            List of search results with title, snippet, and url.
        """

        num_results: int = min(settings.web.MAX_WEB_SEARCH_RESULTS, 20)

        if not self.brave_api_key:
            self._logger.critical("Brave Search API key not configured")
            return self._fallback_search(query, num_results)

        self._logger.debug(f"Performing web search for: {query}")

        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.brave_api_key,
            }
            params = {"q": query, "count": num_results}

            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=settings.web.WEB_REQUEST_TIMEOUT_SECS,
            )
            response.raise_for_status()

            data = response.json()
            items = data.get("web", {}).get("results", [])

            if not items:
                self._logger.warning("No search results found")
                return []

            results: List[WebSearchResult] = [
                WebSearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("description", ""),
                    url=item.get("url", ""),
                )
                for item in items
            ]

            self._logger.debug(f"Retrieved {len(results)} search results")

            return results

        except requests.exceptions.HTTPError as e:
            body = e.response.text if e.response is not None else "<no response body>"
            self._logger.error(f"Error in web search: {e}, response body: {body}")
            return self._fallback_search(query, num_results)
        except Exception as e:
            self._logger.error(f"Error in web search: {e}")
            return self._fallback_search(query, num_results)

    def _fallback_search(self, query: str, num_results: int) -> List[WebSearchResult]:
        """
        Fallback search using DuckDuckGo via the `ddgs` library.
        """

        if not settings.web.WEB_SEARCH_FALLBACK_ENABLED:
            self._logger.warning("Web search fallback is disabled")
            return []

        try:
            raw_results = DDGS().text(query, max_results=num_results)

            results: List[WebSearchResult] = [
                WebSearchResult(
                    title=item.get("title", ""),
                    snippet=item.get("body", ""),
                    url=item.get("href", ""),
                )
                for item in raw_results
            ]

            self._logger.debug(f"Retrieved {len(results)} fallback search results")
            return results

        except DDGSException as e:
            self._logger.error(f"Error in fallback search: {e}")
            return []
        except Exception as e:
            self._logger.error(f"Unexpected error in fallback search: {e}")
            return []

    def _fetch_content(self, result: WebSearchResult) -> Optional[str]:
        """
        Fetch the raw HTML for a search result, falling back to a minimal
        HTML wrapper around the title/snippet if the page can't be fetched.

        This always returns real HTML (never plain text), so a downstream
        HTML-aware converter (e.g. DocumentProcessor.extract) can parse it
        consistently regardless of which path was taken.
        """

        try:
            page_html = self._fetch_page_html(result.url)

            if (
                page_html
                and len(page_html.strip()) >= settings.app.MIN_DOCUMENT_CONTENT_LENGTH
            ):
                return page_html

            self._logger.debug(f"Using title/snippet HTML fallback for {result.url}")
            return (
                "<html><body>"
                f"<h1>{escape(result.title)}</h1>"
                f"<p>{escape(result.snippet)}</p>"
                "</body></html>"
            )

        except Exception as e:
            self._logger.error(f"Error fetching content for {result.url}: {e}")
            return None

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """Return False if the URL resolves to a private or reserved IP address."""
        try:
            hostname = urlparse(url).hostname
            if not hostname:
                return False
            ip = ipaddress.ip_address(socket.gethostbyname(hostname))
            return not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            )
        except Exception:
            return False

    def _fetch_page_html(self, url: str) -> Optional[str]:
        """
        Fetch the raw HTML for a page at the given URL, or return None if any
        error occurs.
        """

        try:
            if not self._is_safe_url(url):
                self._logger.warning(
                    f"Blocked fetch to private/reserved address: {url}"
                )
                return None

            headers = {"User-Agent": settings.web.WEB_USER_AGENT}

            response = requests.get(
                url, headers=headers, timeout=settings.web.WEB_REQUEST_TIMEOUT_SECS
            )
            response.raise_for_status()

            self._logger.debug(
                f"Successfully fetched {len(response.text)} characters of HTML from {url}"
            )
            return response.text

        except Exception as e:
            self._logger.error(f"Error fetching content from {url}: {e}")
            return None
