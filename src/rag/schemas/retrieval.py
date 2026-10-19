from pydantic import Field

from src.shared.utils import CamelCaseSerializer


class GetChunkEmbeddingsConfig(CamelCaseSerializer):
    top_k: int = Field(
        default=15, gt=10, lt=100, description="Number of top chunks to retrieve"
    )
    threshold: float = 0.7
    min_score: float = 0.5
    web_search_enabled: bool = False


class GetChunkEmbeddings(CamelCaseSerializer):

    query: str
    configs: GetChunkEmbeddingsConfig
