from src.shared.utils import CamelCaseSerializer


class GetChunkEmbeddingsConfig(CamelCaseSerializer):
    top_k: int = 15
    threshold: float = 0.7
    min_score: float = 0.5
    web_search_enabled: bool = False


class GetChunkEmbeddings(CamelCaseSerializer):

    query: str
    configs: GetChunkEmbeddingsConfig
