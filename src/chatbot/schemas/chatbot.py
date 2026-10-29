from pydantic import Field

from src.rag.schemas.retrieval import GetChunkEmbeddingsConfig
from src.shared.utils import CamelCaseSerializer


class ChatRequest(CamelCaseSerializer):
    query: str = Field(min_length=1, max_length=2000)
    configs: GetChunkEmbeddingsConfig = Field(default_factory=GetChunkEmbeddingsConfig)


class ChatbotResponse(CamelCaseSerializer):
    answer: str
    # Document filenames and web page titles, without duplicates.
    sources: list[str]
