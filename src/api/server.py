"""
Main entry point to start the API server using Uvicorn.
"""

import uvicorn

from src.api.app import create_app
from src.config.configs import settings

app = create_app()

HOST = settings.app.HOST
PORT = settings.app.PORT
ENV = settings.app.ENV

if __name__ == "__main__":
    uvicorn.run("src.api.server:app", host=HOST, port=PORT, reload=ENV == "development")
