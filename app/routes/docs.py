"""GitBook-style documentation at /docs.

Browsers get the MDUI sidebar layout; agents/curl (`?format=text` or a
non-browser User-Agent) get the raw Markdown source.
"""

from __future__ import annotations

import html
import os

import markdown as md_lib
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from ..negotiation import wants_html
from ..i18n import lang_for, t
from ..ui import page

router = APIRouter()

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "docs")
DOCS_EN_DIR = os.path.join(DOCS_DIR, "en")

PAGES = [
    ("index", "介紹", "Overview"),
    ("quickstart", "快速開始", "Quick start"),
    ("api", "API 參考", "API reference"),
    ("limits", "限制與規範", "Limits"),
    ("legal", "法律條款", "Legal"),
]

_md = md_lib.Markdown(extensions=["fenced_code", "tables"])


def _read(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load(slug: str, lang: str = "zh-TW") -> str | None:
    """`docs/en/<slug>.md` for English readers, `docs/<slug>.md` otherwise.

    `legal.md` is one bilingual file, so it is served as-is either way.
    """
    if lang != "zh-TW" and slug != "legal":
        src = _read(os.path.join(DOCS_EN_DIR, f"{slug}.md"))
        if src is not None:
            return src
    return _read(os.path.join(DOCS_DIR, f"{slug}.md"))


def _docs_shell(lang: str, active: str, body_html: str, slug: str = "index") -> str:
    items = []
    for slug, zh_title, en_title in PAGES:
        title = zh_title if lang == "zh-TW" else en_title
        cls = "mdui-list-item-active" if slug == active else ""
        href = "/docs" if slug == "index" else f"/docs/{slug}"
        items.append(
            f'<mdui-list-item href="{href}" class="{cls}" rounded>'
            f"{html.escape(title)}</mdui-list-item>"
        )
    return page(
        t(lang, "docs_kicker"),
        f"""<div class="docs-layout">
      <mdui-card variant="outlined" class="card-pad docs-nav">
        <mdui-list>{"".join(items)}</mdui-list>
        <mdui-divider></mdui-divider>
        <div class="nav-foot"><a href="https://github.com/ChiuHuang/caveman-drop">GitHub</a> · <a href="/llms.txt">llms.txt</a></div>
      </mdui-card>
      <mdui-card variant="outlined" class="prose-wrap">
        <div class="mdui-prose">{body_html}</div>
      </mdui-card>
    </div>""",
        active="docs",
        lang=lang,
    )


@router.get("/legal")
async def legal_alias(request: Request):
    """/legal is a memorable alias for /docs/legal."""
    return RedirectResponse("/docs/legal", status_code=303)


@router.get("/docs")
async def docs_index(request: Request):
    lang = lang_for(request)
    src = _load("index", lang) or "# Docs\n\nMissing docs/index.md"
    if wants_html(request):
        return HTMLResponse(_docs_shell(lang, "index", _md.convert(src), "index"))
    return PlainTextResponse(src)


@router.get("/docs/{slug}")
async def docs_page(request: Request, slug: str):
    if slug not in {s for s, _, _ in PAGES}:
        return PlainTextResponse("Doc page not found.", status_code=404)
    lang = lang_for(request)
    src = _load(slug, lang)
    if src is None:
        return PlainTextResponse("Doc page not found.", status_code=404)
    if wants_html(request):
        return HTMLResponse(_docs_shell(lang, slug, _md.convert(src), slug))
    return PlainTextResponse(src)
