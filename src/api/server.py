"""
Main entry point to start the API server using Uvicorn.
"""

import uvicorn

from src.config.configs import settings
from src.api.app import create_app

app = create_app()

HOST = settings.app.HOST
PORT = settings.app.PORT

if __name__ == "__main__":
    print(f"Docs available at http://{HOST}:{PORT}/docs")
    uvicorn.run("src.api.server:app", host=HOST, port=PORT, reload=True)
