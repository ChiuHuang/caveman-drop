"""MDUI v2 HTML shell + reusable page components.

Every user-facing route renders through :func:`page` so the whole site shares
one Material Design 3 look (MDUI v2 via CDN, auto dark mode). API clients
never see this — they get JSON/text via content negotiation.
"""

from __future__ import annotations

import html

MDUI_CSS = "https://unpkg.com/mdui@2/mdui.css"
MDUI_JS = "https://unpkg.com/mdui@2/mdui.global.js"
ICON_FONT = "https://fonts.googleapis.com/icon?family=Material+Icons"

NAV = [
    ("home", "Home", "/", "home"),
    ("upload", "Upload", "/upload", "upload"),
    ("api", "API", "/api", "api"),
    ("docs", "Docs", "/docs", "menu_book"),
    ("login", "Login", "/login", "login"),
]


def page(
    title: str,
    body: str,
    active: str = "home",
    extra_head: str = "",
    authed: bool = False,
) -> str:
    nav_items = []
    for key, label, href, icon in NAV:
        if key == "login" and authed:
            label, href, icon = "Logout", "/logout", "logout"
            key = "logout"
        cls = "mdui-list-item-active" if key == active or (
            active == "logout" and key == "logout"
        ) else ""
        nav_items.append(
            f'<mdui-list-item href="{href}" class="{cls}" rounded>'
            f"{html.escape(label)}"
            f'<mdui-icon slot="icon" name="{icon}"></mdui-icon>'
            "</mdui-list-item>"
        )
    return f"""<!DOCTYPE html>
<html lang="en" class="mdui-theme-auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — CaveMan Drop</title>
<link rel="stylesheet" href="{MDUI_CSS}">
<link rel="stylesheet" href="{ICON_FONT}">
<link rel="stylesheet" href="/static/app.css">
<script src="{MDUI_JS}"></script>
{extra_head}
</head>
<body>
<mdui-layout>
  <mdui-top-app-bar>
    <mdui-button-icon id="nav-toggle" icon="menu"></mdui-button-icon>
    <mdui-top-app-bar-title>CaveMan Drop</mdui-top-app-bar-title>
    <div style="flex-grow:1"></div>
    <mdui-button-icon id="theme-toggle" icon="dark_mode"></mdui-button-icon>
  </mdui-top-app-bar>
  <mdui-navigation-drawer id="nav-drawer" close-on-overlay-click>
    <div style="padding:8px">
      <mdui-list>{"".join(nav_items)}</mdui-list>
      <mdui-divider></mdui-divider>
      <div class="nav-foot">Anonymous file sharing.<br>Agents: see <a href="/llms.txt">/llms.txt</a></div>
    </div>
  </mdui-navigation-drawer>
  <mdui-layout-main>
    <main class="page">{body}</main>
    <footer class="foot">CaveMan Drop · text-first API, MDUI UI for browsers</footer>
  </mdui-layout-main>
</mdui-layout>
<mdui-snackbar id="toast" close-on-outside-click></mdui-snackbar>
<script src="/static/app.js"></script>
</body>
</html>"""


def toast(msg: str) -> str:
    return f"<script>window.addEventListener('load',()=>window.toast({msg!r}));</script>"


def endpoint_card(method: str, path: str, desc: str, href: str | None = None) -> str:
    link = (
        f'<a href="{html.escape(href)}"><mdui-button variant="text">Open UI</mdui-button></a>'
        if href
        else ""
    )
    return (
        '<mdui-card variant="outlined" class="ep-card">'
        f'<div class="ep-row"><mdui-chip class="method">{html.escape(method)}</mdui-chip>'
        f'<code class="ep-path">{html.escape(path)}</code></div>'
        f'<p class="ep-desc">{html.escape(desc)}</p>'
        f'<div class="ep-actions">{link}</div>'
        "</mdui-card>"
    )


def file_rows(files: list[dict], folder_id: str, base: str) -> str:
    if not files:
        return '<mdui-card variant="filled" class="empty">No files yet.</mdui-card>'
    rows = []
    for f in files:
        dl = f.get("download_url") or f"{base}/dl/pub/{folder_id}/{f['id']}"
        rows.append(
            "<mdui-list-item>"
            f'<mdui-icon slot="icon" name="description"></mdui-icon>'
            f'<div><div class="fname">{html.escape(f["name"])}</div>'
            f'<div class="fmeta">{f["size"]} bytes · {html.escape(str(f.get("content_type", "")))}</div></div>'
            f'<a slot="end-icon" href="{html.escape(dl)}"><mdui-button-icon icon="download"></mdui-button-icon></a>'
            f'<mdui-button slot="end-icon" variant="text" data-copy="{html.escape(dl)}">Copy</mdui-button>'
            "</mdui-list-item>"
        )
    return f'<mdui-list class="file-list">{"".join(rows)}</mdui-list>'
