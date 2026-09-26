"""MDUI v2 HTML shell + reusable page components (Traditional Chinese UI).

Every user-facing route renders through :func:`page` so the whole site shares
one Material Design 3 look (MDUI v2 via CDN, auto dark mode). API clients
never see this — they get JSON/text via content negotiation.
"""

from __future__ import annotations

import datetime
import html

MDUI_CSS = "https://unpkg.com/mdui@2/mdui.css"
MDUI_JS = "https://unpkg.com/mdui@2/mdui.global.js"
ICON_FONT = "https://fonts.googleapis.com/icon?family=Material+Icons"


def nav_items(active: str, authed: bool) -> list[tuple[str, str, str, str]]:
    items = [
        ("home", "首頁", "/", "home"),
        ("api", "API", "/api", "api"),
        ("docs", "文件", "/docs", "menu_book"),
    ]
    if authed:
        # Private mode: no public upload entry after login.
        items.append(("logout", "登出", "/logout", "logout"))
    else:
        items.insert(1, ("upload", "上傳", "/upload", "upload"))
        items.append(("login", "登入", "/login", "login"))
    return items


def page(
    title: str,
    body: str,
    active: str = "home",
    extra_head: str = "",
    authed: bool = False,
) -> str:
    nav_html = []
    for key, label, href, icon in nav_items(active, authed):
        cls = "mdui-list-item-active" if key == active else ""
        nav_html.append(
            f'<mdui-list-item href="{href}" class="{cls}" rounded>'
            f"{html.escape(label)}"
            f'<mdui-icon slot="icon" name="{icon}"></mdui-icon>'
            "</mdui-list-item>"
        )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant" class="mdui-theme-auto">
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
      <mdui-list>{"".join(nav_html)}</mdui-list>
      <mdui-divider></mdui-divider>
      <div class="nav-foot">匿名檔案分享。<br>機器 / AI 請看 <a href="/llms.txt">/llms.txt</a></div>
    </div>
  </mdui-navigation-drawer>
  <mdui-layout-main>
    <main class="page">{body}</main>
    <footer class="foot">CaveMan Drop · 瀏覽器使用圖形介面，程式與 AI 使用純文字 API</footer>
  </mdui-layout-main>
</mdui-layout>
<mdui-snackbar id="toast" close-on-outside-click></mdui-snackbar>
<script src="/static/app.js"></script>
</body>
</html>"""


def fmt_size(n: int) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_time(ts: float) -> str:
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def toast(msg: str) -> str:
    return f"<script>window.addEventListener('load',()=>window.toast({msg!r}));</script>"


def endpoint_card(method: str, path: str, desc: str, href: str | None = None) -> str:
    link = (
        f'<a href="{html.escape(href)}"><mdui-button variant="text">開啟頁面</mdui-button></a>'
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
    """Public folder file list: download + multi-thread download + preview + copy."""
    if not files:
        return '<mdui-card variant="filled" class="empty">這個資料夾還沒有檔案。</mdui-card>'
    rows = []
    for f in files:
        dl = f.get("download_url") or f"{base}/dl/pub/{folder_id}/{f['id']}"
        preview = f"{dl}?preview=1"
        rows.append(
            "<mdui-list-item>"
            f'<mdui-icon slot="icon" name="description"></mdui-icon>'
            f'<div><div class="fname">{html.escape(f["name"])}</div>'
            f'<div class="fmeta">{fmt_size(f["size"])} · {html.escape(str(f.get("content_type", "")))} · {fmt_time(f.get("ctime", 0))}</div></div>'
            f'<mdui-button-icon slot="end-icon" icon="visibility" data-preview="{html.escape(preview)}" data-name="{html.escape(f["name"])}" title="預覽"></mdui-button-icon>'
            f'<a slot="end-icon" href="{html.escape(dl)}"><mdui-button-icon icon="download" title="下載"></mdui-button-icon></a>'
            f'<mdui-button slot="end-icon" variant="text" data-mt-download="{html.escape(dl)}" data-name="{html.escape(f["name"])}" data-size="{f["size"]}">16 線程下載</mdui-button>'
            f'<mdui-button slot="end-icon" variant="text" data-copy="{html.escape(dl)}">複製連結</mdui-button>'
            "</mdui-list-item>"
        )
    return f'<mdui-list class="file-list">{"".join(rows)}</mdui-list>'


def private_file_rows(files: list[dict], base: str) -> str:
    """Private file list: preview + download + 16-thread download + copy + delete."""
    if not files:
        return '<mdui-card variant="filled" class="empty">還沒有私人檔案，先從上方上傳吧。</mdui-card>'
    rows = []
    for f in files:
        dl = f"{base}/dl/{f['id']}"
        pv = f"{base}/view/{f['id']}"
        rows.append(
            "<mdui-list-item>"
            f'<mdui-icon slot="icon" name="description"></mdui-icon>'
            f'<div><div class="fname">{html.escape(f["name"])}</div>'
            f'<div class="fmeta">{fmt_size(f.get("bytes", 0))} · {fmt_time(f.get("ctime", 0))}</div></div>'
            f'<mdui-button-icon slot="end-icon" icon="visibility" data-preview="{html.escape(pv)}" data-name="{html.escape(f["name"])}" title="預覽"></mdui-button-icon>'
            f'<a slot="end-icon" href="{html.escape(dl)}"><mdui-button-icon icon="download" title="下載"></mdui-button-icon></a>'
            f'<mdui-button slot="end-icon" variant="text" data-mt-download="{html.escape(dl)}" data-name="{html.escape(f["name"])}" data-size="{f.get("bytes", 0)}">16 線程下載</mdui-button>'
            f'<mdui-button slot="end-icon" variant="text" data-copy="{html.escape(dl)}">直接連結</mdui-button>'
            f'<mdui-button slot="end-icon" variant="text" data-delete="{html.escape(base + "/del/" + f["id"])}" data-name="{html.escape(f["name"])}">刪除</mdui-button>'
            "</mdui-list-item>"
        )
    return f'<mdui-list class="file-list">{"".join(rows)}</mdui-list>'


def private_panel(files: list[dict], base: str) -> str:
    """Private-mode dashboard fragment: 16-thread chunked upload + file list."""
    return f"""
        <mdui-card variant="outlined" class="card-pad">
          <h2>上傳檔案（16 線程分段上傳）</h2>
          <p class="muted">大檔案會自動切成 4 MB 分塊，以 16 條並行上傳，斷線重整後可直接重傳。</p>
          <form action="/api/upload_chunk" method="post" data-chunked>
            <div class="form-row">
              <input type="file" name="file" required>
              <mdui-button type="submit">開始上傳</mdui-button>
            </div>
            <mdui-linear-progress data-progress style="display:none"></mdui-linear-progress>
            <p class="muted" data-progress-text></p>
          </form>
        </mdui-card>
        <mdui-card variant="outlined" class="card-pad">
          <h2>私人檔案（{len(files)}）</h2>
          {private_file_rows(files, base)}
        </mdui-card>"""
