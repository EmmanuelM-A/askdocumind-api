"""
Controller for health check endpoints.
Orchestrates between FastAPI routes and service layer.
"""

from fastapi import status
from src.api.services import HealthCheckService
from src.api.utils.response_delivery import create_success_response


class HealthCheckController:
    """Controller for handling health check requests."""

    @staticmethod
    async def get_api_health():
        """
        Handle API health check.
        """

        health_data = await HealthCheckService.check_api_health()

        return create_success_response(
            status_code=status.HTTP_200_OK, success_response_model=health_data
        )

    @staticmethod
    async def get_database_health():
        """
        Handle database connectivity health check.
        """

        db_status = await HealthCheckService.check_database_health()

        return create_success_response(
            status_code=status.HTTP_200_OK, success_response_model=db_status
        )
