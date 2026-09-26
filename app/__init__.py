"""CaveMan Drop application factory."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import storage
from .config import settings
from .negotiation import wants_html
from .routes import docs, pages, private_api, public_api, system
from .ui import page


async def _tmp_sweeper() -> None:
    while True:
        await asyncio.sleep(3600)
        storage.sweep_tmp()


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.sweep_tmp()
    task = asyncio.create_task(_tmp_sweeper())
    try:
        yield
    finally:
        task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="CaveMan Drop", version="2.0.0", docs_url="/swagger", redoc_url=None, lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

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
                    "找不到",
                    '<mdui-card variant="outlined" class="card-pad">'
                    "<h1>404</h1><p>這個網址沒有東西。</p>"
                    '<a href="/"><mdui-button>回首頁</mdui-button></a></mdui-card>',
                ),
                status_code=404,
            )
        return JSONResponse(status_code=404, content={"error": "not found"})

    return app


app = create_app()
