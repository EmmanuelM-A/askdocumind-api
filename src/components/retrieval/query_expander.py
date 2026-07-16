from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.errors.custom_exceptions import server_error, unprocessable_entity_error
from src.logger.base_logger import BaseLogger

_logger = BaseLogger(__name__)


def expand_query(
    query: str, llm: ChatOpenAI, prompt_template: ChatPromptTemplate
) -> str:
    """
    Expands the given query using an LLM to provide more context or related terms.
    """

    if not query.strip():
        raise unprocessable_entity_error(
            message="The provided query is empty or whitespace.",
            error_code="EMPTY_QUERY",
        )

    expansion_chain = prompt_template | llm | StrOutputParser()

    try:
        expanded_query = expansion_chain.invoke({"query": query})
    except Exception as e:
        raise server_error(
            message="The AI service is temporarily unavailable. Please try again shortly.",
            error_code="LLM_SERVICE_ERROR",
            stack_trace=str(e),
        )

    expanded_query = expanded_query.strip()

    if not expanded_query:
        raise server_error(
            message="The LLM returned an empty expanded query.",
            error_code="LLM_EMPTY_RESPONSE",
        )

    if len(expanded_query) < len(query):
        _logger.warning("The expanded query is not longer than the original query!")
    elif len(expanded_query) == len(query):
        _logger.warning(
            "The expanded query is identical to the original query! So no expansion was performed."
        )
    else:
        _logger.info("The query was successfully expanded.")

    return expanded_query
