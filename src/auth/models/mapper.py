"""
This module contains DTOs for user and auth related data transfer.
"""

from uuid import UUID

from src.shared.utils import CamelCaseSerializer


class ViewableUser(CamelCaseSerializer):
    """
    Represents a viewable user.
    """

    id: UUID
    created_at: str
    last_seen_at: str
