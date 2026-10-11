import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.config.configs import settings
from src.exceptions import unprocessable_content_error, server_error
from src.rag.services.expand.query_expander import QueryExpander


class QueryExpanderConfig(BaseModel):

    max_attempts: int = 3
    prompt_template: ChatPromptTemplate


"""
Strips stray tags or labels the model might echo back despite the
prompt instructions.
"""
_STRIP_OUTPUT_STRAYS = re.compile(
    r"^\s*(?:<query>|</query>|expanded query:|query:)\s*", re.IGNORECASE
)


class LangChainOpenAIQueryExpander(QueryExpander):
    def __init__(self, config: QueryExpanderConfig) -> None:
        self._llm: ChatOpenAI = ChatOpenAI(
            model=settings.llm.MODEL_NAME,
            temperature=settings.llm.TEMPERATURE,
            timeout=settings.llm.REQUEST_TIMEOUT_SECS,
            max_retries=settings.llm.MAX_RETRIES,
            max_completion_tokens=settings.llm.MAX_OUTPUT_TOKENS,
        )
        self._chain = (
            config.prompt_template | self._llm | StrOutputParser()
        ).with_retry(
            stop_after_attempt=config.max_attempts, wait_exponential_jitter=True
        )

    async def expand(self, query) -> str:

        query = query.strip()

        if not query:
            raise unprocessable_content_error(
                message="The query string is empty or contains only whitespace.",
                error_code="INVALID_QUERY",
            )

        try:
            response = (await self._chain.ainvoke({"query": query})).strip()
        except Exception as e:
            raise server_error(
                message="An error occurred whilst expanding the query.",
                error_code="QUERY_EXPANSION_ERROR",
            ) from e

        if not response:
            raise server_error(
                message="The query expansion returned an empty response.",
                error_code="QUERY_EXPANSION_FAILED",
            )

        return _STRIP_OUTPUT_STRAYS.sub("", response).strip()
