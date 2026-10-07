"""
Custom base error class for API exceptions.

This class is used throughout the API to raise structured, JSON-based
errors that integrate seamlessly with FastAPI’s exception handling.
"""

from typing import Dict

from fastapi import HTTPException


class ApiException(HTTPException):
    """
    Base exception class for structured API exceptions.
    """

    def __init__(
        self,
        message: str,
        error_code: str,
        status_code: int,
        error_details: Dict[str, str] | None = None,
        cause: BaseException | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.error_code = error_code
        self.error_details = error_details
        if cause is not None:
            self.__cause__ = cause
