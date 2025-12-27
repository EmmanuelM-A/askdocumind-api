"""
Service layer for API and database health checks.
Handles system diagnostics and status reporting logic.
"""

from src.errors.custom_exceptions import throw_database_error
from src.database.connection import get_database_connection
from src.utils.api_responses import SuccessResponseModel
from sqlalchemy import text


class HealthCheckService:
    """Service class responsible for performing health diagnostics."""

    @staticmethod
    async def check_api_health() -> SuccessResponseModel:
        """
        Returns API health status and system information.
        """

        return SuccessResponseModel(
            message="The API is healthy and running.",
            data={
                "status": "OK",
            },
        )

    @staticmethod
    async def check_database_health() -> SuccessResponseModel | None:
        """
        Verifies database connectivity by running a lightweight query.
        """

        try:
            async with get_database_connection().get_session() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar_one_or_none()

            return SuccessResponseModel(
                message="Database connection is healthy.", data={"status": "OK"}
            )
        except Exception as e:
            throw_database_error(
                message="Failed to connect to the database during health check.",
                error_code="DB_CONNECTION_FAILED",
                stack_trace=str(e),
            )

            return None
