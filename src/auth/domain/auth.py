from uuid import UUID

from pydantic import BaseModel


class AnonymousTokenPayload(BaseModel):
    """
    Represents the payload of an anonymous JWT token.
    """

    sub: UUID
    iat: float
    exp: float
