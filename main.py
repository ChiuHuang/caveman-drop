"""CaveMan Drop entry point. Run with `uv run main.py` or `uvicorn main:app`."""

import uvicorn

from app import app
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port)
