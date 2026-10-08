from uuid import UUID

from pydantic import BaseModel


class AnonymousTokenPayload(BaseModel):
    """
    Represents the payload of an anonymous JWT token.
    """

    user_id: UUID
    iat: float
    exp: float

    def to_dict(self) -> dict:
        """
        Convert the payload to a dictionary.
        """
        return {
            "user_id": str(self.user_id),
            "iat": self.iat,
            "exp": self.exp,
        }
