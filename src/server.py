"""
Main entry point to start the API server using uvicorn.
"""

import uvicorn

from src.app import create_app
from src.config.configs import settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "src.server:app",
        host=settings.server.HOST,
        port=settings.server.PORT,
        reload=(settings.server.ENV == "development"),
        limit_concurrency=settings.server.MAX_CONCURRENCY,
        proxy_headers=True,
        forwarded_allow_ips=settings.server.FORWARDED_ALLOW_IPS,
        # RequestLoggerMiddleware logs each request in production
        access_log=(settings.server.ENV != "production"),
    )
