import logging
import re

import openai
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.config.configs import settings
from src.exceptions import server_error, unprocessable_content_error
from src.rag.services.expand.query_expander import QueryExpander

_logger = logging.getLogger(__name__)


class QueryExpanderConfig(BaseModel):
    max_attempts: int = 3
    prompt_template: ChatPromptTemplate


# The prompt wraps the query in <query> tags and treats everything inside
# them as data. A query that contains these tags could close the wrapper
# early, so they are removed from the input, and from the model output,
# where they can only be stray echoes of the wrapper.
_QUERY_TAG = re.compile(r"</?query>", re.IGNORECASE)

# Labels the model sometimes echoes back despite the prompt instructions.
_LABEL_PREFIX = re.compile(r"^\s*(?:expanded query|query)\s*:\s*", re.IGNORECASE)

# Only transient failures are worth retrying. Auth errors, bad requests and
# template errors fail the same way on every attempt. APITimeoutError is a
# subclass of APIConnectionError, so timeouts are covered too.
_TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)

# Output guard: the prompt asks for a short expansion. A reply far longer
# than the query points to a model that ignored the prompt, for example
# after a successful injection, so the original query is used instead.
_MAX_EXPANSION_RATIO = 10
_MIN_OUTPUT_LIMIT = 300


class LangChainOpenAIQueryExpander(QueryExpander):
    def __init__(
        self, config: QueryExpanderConfig, llm: Runnable | None = None
    ) -> None:
        self._llm: Runnable = (
            llm
            if llm is not None
            else ChatOpenAI(
                api_key=settings.llm.OPENAI_API_KEY,
                model=settings.llm.MODEL_NAME,
                temperature=settings.llm.TEMPERATURE,
                timeout=settings.llm.REQUEST_TIMEOUT_SECS,
                max_retries=settings.llm.MAX_RETRIES,
                max_completion_tokens=settings.llm.MAX_OUTPUT_TOKENS,
            )
        )
        self._chain = (
            config.prompt_template | self._llm | StrOutputParser()
        ).with_retry(
            retry_if_exception_type=_TRANSIENT_ERRORS,
            stop_after_attempt=config.max_attempts,
            wait_exponential_jitter=True,
        )

    async def expand(self, query: str) -> str:

        query = _QUERY_TAG.sub("", query).strip()

        if not query:
            raise unprocessable_content_error(
                message="The query string is empty or contains only whitespace.",
                error_code="INVALID_QUERY",
            )

        try:
            response = await self._chain.ainvoke({"query": query})
        except Exception as e:
            raise server_error(
                message="An error occurred whilst expanding the query.",
                error_code="QUERY_EXPANSION_ERROR",
            ) from e

        expanded = self._clean_response(response, query)

        if not expanded:
            raise server_error(
                message="The query expansion returned an empty response.",
                error_code="QUERY_EXPANSION_FAILED",
            )

        limit = max(len(query) * _MAX_EXPANSION_RATIO, _MIN_OUTPUT_LIMIT)

        if len(expanded) > limit:
            _logger.warning(
                "Query expansion was %d characters for a %d character query. "
                "Using the original query.",
                len(expanded),
                len(query),
            )
            return query

        return expanded

    @staticmethod
    def _clean_response(response: str, query: str) -> str:
        """
        Remove stray <query> tags and echoed labels from the model output.

        A label is kept when the original query itself starts with it, since
        the prompt tells the model to return such a query unchanged.
        """
        cleaned = _QUERY_TAG.sub("", response).strip()
        query_start = query.lower()

        while (match := _LABEL_PREFIX.match(cleaned)) is not None:
            if query_start.startswith(match.group(0).strip().lower()):
                break
            cleaned = cleaned[match.end() :]

        return cleaned.strip()
