from uuid import UUID

from pydantic import BaseModel


class AnonymousTokenPayload(BaseModel):
    """
    Represents the payload of an anonymous JWT token.
    """

    user_id: UUID
    iat: float
    exp: float
