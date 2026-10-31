from pydantic import BaseModel, Field

from src.rag.models.mapper import ViewableChunkEmbedding
from src.shared.utils import CamelCaseSerializer


class GetChunkEmbeddingsConfig(CamelCaseSerializer):
    top_k: int = Field(
        default=15, ge=1, le=100, description="Number of top chunks to retrieve"
    )
    threshold: float = Field(default=0.35, ge=0, le=1)
    web_search_enabled: bool = False


class GetChunkEmbeddings(CamelCaseSerializer):
    query: str
    configs: GetChunkEmbeddingsConfig


class WebResult(BaseModel):
    url: str
    title: str
    content: str


class RetrievalResults(BaseModel):
    expanded_query: str
    chunks: list[ViewableChunkEmbedding]
    additional: list[WebResult]
