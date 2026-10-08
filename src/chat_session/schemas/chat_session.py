from src.shared.utils import CamelCaseSerializer


class CreateChatSession(CamelCaseSerializer):
    """
    Represents the data required to create a new chat session.
    """

    title: str
