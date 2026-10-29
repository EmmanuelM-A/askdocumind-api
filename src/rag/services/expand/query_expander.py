from abc import ABC, abstractmethod


class QueryExpander(ABC):
    """
    Abstract base class for query expansion.
    """

    @abstractmethod
    async def expand(self, query: str) -> str:
        """
        Expands the given query and returns the expanded version.
        :param query: The original query string to be expanded.
        :return: The expanded query string.
        """
        raise NotImplementedError("Subclasses must implement this method.")
