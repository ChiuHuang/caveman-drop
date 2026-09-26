"""CaveMan Drop application factory."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .negotiation import wants_html
from .routes import docs, pages, private_api, public_api, system
from .ui import page


def create_app() -> FastAPI:
    # docs_url is moved aside: our GitBook-style guides live at /docs.
    app = FastAPI(title="CaveMan Drop", version="2.0.0", docs_url="/swagger", redoc_url=None)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

    # CORS is open so the public upload/download API can be called from any
    # origin. allow_credentials is False because credentialed requests can't
    # combine with a wildcard origin; the private dashboard is same-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    app.include_router(pages.router)
    app.include_router(public_api.router)
    app.include_router(private_api.router)
    app.include_router(system.router)
    app.include_router(docs.router)

    @app.exception_handler(404)
    async def not_found(request: Request, _exc: Exception):
        if wants_html(request):
            return HTMLResponse(
                page(
                    "Not found",
                    '<mdui-card variant="outlined" class="card-pad">'
                    "<h1>404</h1><p>Nothing lives at this URL.</p>"
                    '<a href="/"><mdui-button>Go home</mdui-button></a></mdui-card>',
                ),
                status_code=404,
            )
        return JSONResponse(status_code=404, content={"error": "not found"})

    return app


app = create_app()
