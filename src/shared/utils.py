"""
Shared utilities for the project.
"""

from pydantic import BaseModel
from pydantic.alias_generators import to_camel


class CamelCaseSerializer(BaseModel):
    """
    A Pydantic BaseModel that automatically converts field names to camelCase
    when serializing to JSON. This is useful for APIs that expect camelCase
    keys in their JSON payloads.
    """

    model_config = {"alias_generator": to_camel, "populate_by_name": True}
