"""
Main entry point to start the API server using uvicorn.
"""

import uvicorn

from src.app import create_app
from src.config.configs import settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        f"src.server:app",
        port=settings.server.PORT,
        reload=(settings.server.ENV == "development"),
        limit_concurrency=settings.server.MAX_CONCURRENCY,
    )
