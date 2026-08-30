import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import APIError, APITimeoutError, RateLimitError

from src.errors.custom_exceptions import server_error, unprocessable_entity_error
from src.logger.base_logger import BaseLogger

_logger = BaseLogger(__name__)

# Strips stray tags or labels the model might echo back despite the
# prompt's "output only the query text" instruction.
_STRAY_OUTPUT_PATTERN = re.compile(
    r"^\s*(?:<query>|</query>|expanded query:|query:)\s*", re.IGNORECASE
)


def expand_query(
    query: str, llm: ChatOpenAI, prompt_template: ChatPromptTemplate
) -> str:
    """
    Expands a query using an LLM to add context and related terms, so a
    document search system has more to match against.

    The prompt instructs the LLM to leave the query unchanged when it is
    already specific, or when the query looks like an attempt to instruct
    the model rather than a genuine search topic. Both cases are expected
    behavior, not failures, so callers should not assume the result always
    differs from the input.

    Raises:
        ApiException (422, EMPTY_QUERY): the query is empty or whitespace.
        ApiException (500, LLM_SERVICE_ERROR): the LLM call failed.
    """

    if not query.strip():
        raise unprocessable_entity_error(
            message="The provided query is empty or whitespace.",
            error_code="EMPTY_QUERY",
        )

    expansion_chain = prompt_template | llm | StrOutputParser()

    try:
        expanded_query = expansion_chain.invoke({"query": query})
    except (APITimeoutError, RateLimitError, APIError) as e:
        raise server_error(
            message="The AI service is temporarily unavailable. Please try again shortly.",
            error_code="LLM_SERVICE_ERROR",
            stack_trace=str(e),
        )
    except Exception as e:  # noqa: BLE001
        raise server_error(
            message="The query could not be expanded due to an internal error.",
            error_code="QUERY_EXPANSION_ERROR",
            stack_trace=str(e),
        )

    expanded_query = _STRAY_OUTPUT_PATTERN.sub("", expanded_query).strip()

    if not expanded_query:
        _logger.warning(
            "The LLM returned an empty expanded query. Falling back to the original."
        )
        return query

    if len(expanded_query) < len(query):
        _logger.warning("The expanded query is not longer than the original query!")
    elif expanded_query == query:
        _logger.warning(
            "The expanded query is identical to the original query! So no expansion was performed."
        )
    else:
        _logger.info("The query was successfully expanded.")

    _logger.debug(f"Expanded query: '{expanded_query}' | Original query: '{query}'")

    return expanded_query
