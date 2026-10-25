from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from src.rag.schemas.retrieval import GetChunkEmbeddingsConfig
from src.shared.utils import CamelCaseSerializer


class ChatRequest(CamelCaseSerializer):
    query: str = Field(min_length=1, max_length=2000)
    configs: GetChunkEmbeddingsConfig = Field(default_factory=GetChunkEmbeddingsConfig)


class DocumentSource(CamelCaseSerializer):
    type: Literal["document"] = "document"
    document_id: UUID
    chunk_index: int


class WebSource(CamelCaseSerializer):
    type: Literal["web"] = "web"
    url: str
    title: str


Source = Annotated[DocumentSource | WebSource, Field(discriminator="type")]


class ChatbotResponse(CamelCaseSerializer):
    answer: str
    sources: list[Source]
