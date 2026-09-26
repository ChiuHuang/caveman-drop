"""GitBook-style documentation at /docs.

Browsers get the MDUI sidebar layout; agents/curl (`?format=text` or a
non-browser User-Agent) get the raw Markdown source.
"""

from __future__ import annotations

import html
import os

import markdown as md_lib
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from ..negotiation import wants_html
from ..ui import page

router = APIRouter()

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "docs")

PAGES = [
    ("index", "介紹"),
    ("quickstart", "快速開始"),
    ("api", "API 參考"),
    ("limits", "限制與規範"),
]

_md = md_lib.Markdown(extensions=["fenced_code", "tables"])


def _load(slug: str) -> str | None:
    path = os.path.join(DOCS_DIR, f"{slug}.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _docs_shell(active: str, body_html: str) -> str:
    items = []
    for slug, title in PAGES:
        cls = "mdui-list-item-active" if slug == active else ""
        href = "/docs" if slug == "index" else f"/docs/{slug}"
        items.append(
            f'<mdui-list-item href="{href}" class="{cls}" rounded>'
            f"{html.escape(title)}</mdui-list-item>"
        )
    return page(
        "Docs",
        f"""<div class="docs-layout">
      <mdui-card variant="outlined" class="card-pad docs-nav">
        <mdui-list>{"".join(items)}</mdui-list>
      </mdui-card>
      <mdui-card variant="outlined" class="prose-wrap">
        <div class="mdui-prose">{body_html}</div>
      </mdui-card>
    </div>""",
        active="docs",
        extra_head='<link rel="stylesheet" href="https://unpkg.com/mdui@2/mdui-prose.css">',
    )


@router.get("/docs")
async def docs_index(request: Request):
    src = _load("index") or "# Docs\n\nMissing docs/index.md"
    if wants_html(request):
        return HTMLResponse(_docs_shell("index", _md.convert(src)))
    return PlainTextResponse(src)


@router.get("/docs/{slug}")
async def docs_page(request: Request, slug: str):
    if slug not in {s for s, _ in PAGES}:
        return PlainTextResponse("Doc page not found.", status_code=404)
    src = _load(slug)
    if src is None:
        return PlainTextResponse("Doc page not found.", status_code=404)
    if wants_html(request):
        return HTMLResponse(_docs_shell(slug, _md.convert(src)))
    return PlainTextResponse(src)
