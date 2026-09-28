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


TOS_TEXT = "使用須知：僅限合法用途；公開檔案任何人可下載，違規內容直接刪除。"


def tos_banner() -> str:
    """Slim site-wide rules strip at the top; dismiss once per browser."""
    return (
        '<div class="tos" data-tos>'
        f'<mdui-icon name="gavel" size="18px"></mdui-icon>'
        f"<span>{html.escape(TOS_TEXT)}</span>"
        '<mdui-button-icon icon="close" data-tos-close title="關閉"></mdui-button-icon>'
        "</div>"
    )


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
      <div class="nav-foot">匿名檔案分享 · <a href="https://github.com/ChiuHuang/caveman-drop">GitHub</a><br>機器 / AI 請看 <a href="/llms.txt">/llms.txt</a></div>
    </div>
  </mdui-navigation-drawer>
  <mdui-layout-main>
    <main class="page" data-droproot>
      {tos_banner()}
      {body}
      <div class="drophint" data-drophint hidden>放開手上傳</div>
    </main>
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


def limits_note() -> str:
    from .config import settings

    return (
        '<p class="muted limits-first">'
        f"單檔上限 {settings.max_file_size // 1024**3} GB・"
        f"資料夾每 {settings.bw_window_seconds // 60} 分鐘合計上限 "
        f"{settings.bw_folder_hard_bytes // 1024**3} GB・超量自動降速。</p>"
    )


def thread_panel() -> str:
    """IDM-style upload monitor: overall bar + segment map + 16 thread rows."""
    return """<div class="tp" data-tp hidden>
      <div class="tp-top">
        <strong data-tp-pct>0%</strong>
        <span data-tp-speed class="tpspeed"></span>
        <span data-tp-note class="tp-note"></span>
      </div>
      <mdui-linear-progress data-tp-bar></mdui-linear-progress>
      <div class="tp-seglabel muted">分段：<span data-tp-segcount></span></div>
      <div class="segbar" data-tp-segs></div>
      <table class="tptable">
        <thead><tr><th>No</th><th>狀態</th></tr></thead>
        <tbody data-tp-rows></tbody>
      </table>
      <div class="form-row">
        <mdui-button variant="outlined" data-tp-pause>暫停</mdui-button>
      </div>
    </div>"""


def endpoint_card(method: str, path: str, desc: str, href: str | None = None) -> str:
    link = (
        f'<a href="{html.escape(href)}"><mdui-button variant="text">開啟頁面</mdui-button></a>'
        if href
        else ""
    )
    return (
        '<mdui-card variant="outlined" class="ep-card">'
        f'<div class="ep-method"><span class="ep-verb">{html.escape(method)}</span> '
        f"<code>{html.escape(path)}</code></div>"
        f'<p class="ep-desc">{html.escape(desc)}</p>'
        f'<div class="ep-actions">{link}</div>'
        "</mdui-card>"
    )


def _meta_line(f: dict, with_type: bool = True) -> str:
    """`652 B · 3 分前 · free-text description` for one file row."""
    bits = [fmt_size(f.get("bytes", f.get("size", 0)) if "bytes" in f else f.get("size", 0))]
    if with_type and f.get("content_type"):
        bits.append(str(f["content_type"]))
    bits.append(fmt_time(f.get("ctime", 0)))
    desc = str(f.get("description", "") or "")
    if desc:
        bits.append(desc)
    return " · ".join(html.escape(b) for b in bits if b)


def file_rows(files: list[dict], folder_id: str, base: str) -> str:
    """Public folder file list: preview + download + copy (one download path)."""
    if not files:
        return '<mdui-card variant="filled" class="empty">這個資料夾還沒有檔案。</mdui-card>'
    rows = []
    for f in files:
        dl = f.get("download_url") or f"{base}/dl/pub/{folder_id}/{f['id']}"
        preview = f"{dl}?preview=1"
        short = f.get("short_url") or ""
        copy_target = short or dl
        rows.append(
            "<mdui-list-item>"
            f'<mdui-icon slot="icon" name="description"></mdui-icon>'
            f'<div><div class="fname">{html.escape(f["name"])}</div>'
            f'<div class="fmeta">{_meta_line(f)}</div></div>'
            f'<mdui-button-icon slot="end-icon" icon="visibility" data-preview="{html.escape(preview)}" data-name="{html.escape(f["name"])}" title="預覽"></mdui-button-icon>'
            f'<mdui-button-icon slot="end-icon" icon="download" data-mt-download="{html.escape(dl)}" data-name="{html.escape(f["name"])}" data-size="{f["size"]}" title="下載"></mdui-button-icon>'
            f'<mdui-button slot="end-icon" variant="text" data-copy="{html.escape(copy_target)}">複製連結</mdui-button>'
            "</mdui-list-item>"
        )
    return f'<mdui-list class="file-list">{"".join(rows)}</mdui-list>'


def _drop_attrs(scope: str, folder_id: str = "", label: str = "") -> str:
    """Marks a card as a drop target: scope + target folder id ("" = uncategorised)."""
    return (
        f'data-dropscope="{html.escape(scope)}" data-dropfolder="{html.escape(folder_id)}"'
        + (f' data-droplabel="{html.escape(label)}"' if label else "")
    )


def private_file_rows(files: list[dict], base: str, scope: str = "private") -> str:
    """File list: preview + download + copy + delete, draggable to move between folders.

    Set `dl` on an entry to override the download path (public files live under
    /dl/pub/<folder>/ or /dl/s/, private ones under /dl/).
    """
    if not files:
        return '<mdui-card variant="filled" class="empty">還沒有檔案。</mdui-card>'
    rows = []
    for f in files:
        dl = f.get("dl") or f"{base}/dl/{f['id']}"
        pv = f"{base}/view/{f['id']}" if scope == "private" else f"{dl}?preview=1"
        del_url = f.get("delete_url") or (base + "/del/" + f["id"])
        rows.append(
            "<mdui-list-item"
            f' draggable="true" data-move="{html.escape(f["id"])}" data-scope="{html.escape(scope)}"'
            f' data-from="{html.escape(f.get("folder_id", "") or "")}"'
            f' data-name="{html.escape(f["name"])}"'
            f' data-sort-name="{html.escape(f["name"].lower())}"'
            f' data-sort-size="{int(f.get("bytes", f.get("size", 0)))}"'
            f' data-sort-time="{float(f.get("ctime", 0))}"'
            ">"
            f'<mdui-icon slot="icon" name="description"></mdui-icon>'
            f'<div><div class="fname">{html.escape(f["name"])}</div>'
            f'<div class="fmeta">{_meta_line(f, with_type=False)}</div></div>'
            f'<mdui-button-icon slot="end-icon" icon="visibility" data-preview="{html.escape(pv)}" data-name="{html.escape(f["name"])}" title="預覽"></mdui-button-icon>'
            f'<mdui-button-icon slot="end-icon" icon="download" data-mt-download="{html.escape(dl)}" data-name="{html.escape(f["name"])}" data-size="{f.get("bytes", f.get("size", 0))}" title="下載"></mdui-button-icon>'
            f'<mdui-button slot="end-icon" variant="text" data-copy="{html.escape(dl)}">直接連結</mdui-button>'
            f'<mdui-button slot="end-icon" variant="text" data-delete="{html.escape(del_url)}"'
            + (' data-delete-post="1"' if f.get("delete_post") else "")
            + f' data-name="{html.escape(f["name"])}">刪除</mdui-button>'
            "</mdui-list-item>"
        )
    return f'<mdui-list class="file-list">{"".join(rows)}</mdui-list>'


def sort_bar() -> str:
    return """<div class="sortbar" data-sortbar data-dir="desc" data-by="time">
      <span class="muted">排序：</span>
      <mdui-button variant="filled" data-sort-by="time">時間</mdui-button>
      <mdui-button variant="text" data-sort-by="size">大小</mdui-button>
      <mdui-button variant="text" data-sort-by="name">名稱</mdui-button>
      <mdui-button-icon data-sort-dir icon="arrow_downward" title="切換順序"></mdui-button-icon>
    </div>"""


def share_file_rows(files: list[dict], token: str, base: str) -> str:
    """Shared folder rows: preview + download + copy, no delete."""
    if not files:
        return '<mdui-card variant="filled" class="empty">這個資料夾還沒有檔案。</mdui-card>'
    rows = []
    for f in files:
        dl = f"{base}/dl/sh/{token}/{f['id']}"
        rows.append(
            "<mdui-list-item>"
            f'<mdui-icon slot="icon" name="description"></mdui-icon>'
            f'<div><div class="fname">{html.escape(f["name"])}</div>'
            f'<div class="fmeta">{_meta_line(f, with_type=False)}</div></div>'
            f'<mdui-button-icon slot="end-icon" icon="visibility" data-preview="{html.escape(dl)}?preview=1" data-name="{html.escape(f["name"])}" title="預覽"></mdui-button-icon>'
            f'<mdui-button-icon slot="end-icon" icon="download" data-mt-download="{html.escape(dl)}" data-name="{html.escape(f["name"])}" data-size="{f.get("bytes", 0)}" title="下載"></mdui-button-icon>'
            f'<mdui-button slot="end-icon" variant="text" data-copy="{html.escape(dl)}">複製連結</mdui-button>'
            "</mdui-list-item>"
        )
    return f'<mdui-list class="file-list">{"".join(rows)}</mdui-list>'


def _private_upload_card(files: list[dict], folders: dict) -> str:
    opts = '<option value="">未分類</option>' + "".join(
        f'<option value="{html.escape(fid)}">{html.escape(m.get("name", ""))}</option>'
        for fid, m in folders.items()
    )
    return f"""
        <mdui-card variant="outlined" class="card-pad">
          <h2>上傳檔案</h2>
          <form action="/api/upload_chunk" method="post" data-chunked data-merge="/api/merge_chunks" data-probe="/api/probe">
            <div class="form-row">
              <input type="file" name="file" required multiple>
              <select name="folder_id" class="folderselect" title="上傳到">{opts}</select>
              <mdui-button type="submit" icon="cloud_upload">上傳</mdui-button>
            </div>
            <div class="upfield">
              <mdui-text-field name="description" label="說明（選填）"></mdui-text-field>
            </div>
            {thread_panel()}
            <div data-upload-result></div>
          </form>
        </mdui-card>"""


def _folder_card(fid: str, name: str, files: list[dict], base: str, shares: dict) -> str:
    srows = "".join(
        f'<div class="rlink"><span class="rlink-label">{"僅檢視" if s.get("mode") == "view" else "可上傳"}</span>'
        f"<code>{html.escape(base + '/s/' + t)}</code>"
        '<span class="rlink-btns">'
        f'<mdui-button variant="text" data-copy="{html.escape(base + "/s/" + t)}">複製</mdui-button>'
        f'<mdui-button variant="text" data-unshare="{html.escape(t)}">取消</mdui-button>'
        "</span></div>"
        for t, s in shares.items()
        if s.get("folder_id") == fid
    )
    return f"""
        <mdui-card variant="outlined" class="card-pad fcard" {_drop_attrs("private", fid, name)}>
          <h2><mdui-icon name="folder" size="20px"></mdui-icon>{html.escape(name)}（{len(files)}）</h2>
          <div class="sharebox">
            {srows}
            <div class="form-row">
              <mdui-button variant="outlined" data-share-create="{html.escape(fid)}" data-mode="view">檢視連結</mdui-button>
              <mdui-button variant="outlined" data-share-create="{html.escape(fid)}" data-mode="upload">上傳連結</mdui-button>
              <mdui-button variant="text" data-delete-dir="{html.escape(base + "/deldir/" + fid)}" data-name="{html.escape(name)}" data-count="{len(files)}">刪除</mdui-button>
            </div>
          </div>
          {sort_bar()}
          {private_file_rows(files, base)}
        </mdui-card>"""


def _public_folder_card(f: dict, base: str) -> str:
    return f"""
        <mdui-card variant="outlined" class="card-pad fcard" {_drop_attrs("public", f["id"], f["name"])}>
          <h2><mdui-icon name="folder" size="20px"></mdui-icon>{html.escape(f["name"])}（{f["count"]}）</h2>
          <div class="form-row">
            <a href="{html.escape(base + "/f/" + f["id"])}"><mdui-button variant="text">開啟</mdui-button></a>
            <mdui-button variant="text" data-copy="{html.escape(base + "/f/" + f["id"])}">複製連結</mdui-button>
            <mdui-button variant="text" data-delpubdir="{html.escape(base + "/delpubdir/" + f["id"])}" data-name="{html.escape(f["name"])}" data-count="{f["count"]}">刪除</mdui-button>
          </div>
        </mdui-card>"""


def private_panel(
    files: list[dict],
    base: str,
    folders: dict,
    shares: dict,
    public: list[dict] | None = None,
    public_folders: list[dict] | None = None,
) -> str:
    """Admin: everything (private + public) in tabs, drag and drop everywhere."""
    public = public or []
    public_folders = public_folders or []
    uncat = [f for f in files if not f.get("folder")]
    grouped = {fid: [f for f in files if f.get("folder") == fid] for fid in folders}
    for f in public:  # public files carry their own download path
        f["bytes"] = f.get("size", 0)
        f["dl"] = (
            f"{base}/dl/pub/{f['folder_id']}/{f['id']}" if f.get("folder_id") else f"{base}/dl/s/{f['id']}"
        )
        f["delete_url"] = f"{base}/delpub/{f['id']}"
        f["delete_post"] = True
    everything = sorted(files + public, key=lambda x: x.get("ctime", 0), reverse=True)
    n_priv = len(files)
    n_pub = len(public)

    folder_tab = "".join(_folder_card(fid, m.get("name", ""), grouped.get(fid, []), base, shares)
                         for fid, m in folders.items())
    if not folders:
        folder_tab = '<mdui-card variant="filled" class="empty">還沒有私人資料夾。</mdui-card>'
    pub_tab = "".join(_public_folder_card(f, base) for f in public_folders)

    return f"""
        <mdui-tabs value="all" data-tabs>
          <mdui-tab value="all">全部（{n_priv + n_pub}）</mdui-tab>
          <mdui-tab value="private">私人（{n_priv}）</mdui-tab>
          <mdui-tab value="folders">資料夾（{len(folders)}）</mdui-tab>
          <mdui-tab value="public">公開（{n_pub}）</mdui-tab>
        </mdui-tabs>

        <div data-tabpanel="all">
          {sort_bar()}
          {private_file_rows(everything, base, scope="mixed")}
        </div>

        <div data-tabpanel="private" hidden>
          {sort_bar()}
          {_private_upload_card(files, folders)}
          {private_file_rows(uncat, base)}
        </div>

        <div data-tabpanel="folders" hidden>
          <mdui-card variant="outlined" class="card-pad">
            <h2>新增資料夾</h2>
            <form data-mkdir>
              <div class="form-row">
                <div class="upfield">
                  <mdui-text-field name="name" label="資料夾名稱" required></mdui-text-field>
                </div>
                <mdui-button type="submit" icon="create_new_folder">建立</mdui-button>
              </div>
            </form>
          </mdui-card>
          {folder_tab}
        </div>

        <div data-tabpanel="public" hidden>
          {public_upload_form()}
          <mdui-card variant="outlined" class="card-pad">
            <h2>公開資料夾（{len(public_folders)}）</h2>
            {pub_tab or '<mdui-card variant="filled" class="empty">還沒有公開資料夾。</mdui-card>'}
          </mdui-card>
          <mdui-card variant="outlined" class="card-pad">
            <h2>公開檔案（{n_pub}）</h2>
            {sort_bar()}
            {private_file_rows(public, base, scope="public")}
          </mdui-card>
        </div>"""


def _upload_row(folder: str | None = None) -> str:
    """File picker row + optional folder/description fields, one per line."""
    if folder:
        field = f'<input type="hidden" name="folder" value="{html.escape(folder)}">'
    else:
        field = """
              <div class="upfield">
                <mdui-text-field name="folder" label="資料夾（選填）"></mdui-text-field>
              </div>"""
    return f"""
              <div class="form-row">
                <input type="file" name="file" multiple required>
                <mdui-button type="submit" icon="cloud_upload">{"加進資料夾" if folder else "上傳"}</mdui-button>
              </div>
              {field}
              <div class="upfield">
                <mdui-text-field name="description" label="說明（選填）"></mdui-text-field>
              </div>"""


def public_upload_form(folder_id: str | None = None) -> str:
    """Public upload UI. Folder page: join-only form. Else: upload/create tabs."""
    form = f"""
            {limits_note()}
            <form action="/api/public/chunk" method="post" data-chunked data-merge="/api/public/merge_chunks" data-public="1" data-probe="/api/public/probe">
              {_upload_row(folder_id)}
              {thread_panel()}
            </form>
            <div data-upload-result></div>"""
    if folder_id:
        return form
    return f"""
            <mdui-tabs value="up" data-tabs>
              <mdui-tab value="up">上傳檔案</mdui-tab>
              <mdui-tab value="mkdir">建立資料夾</mdui-tab>
            </mdui-tabs>
            <div data-tabpanel="up">
              {form}
            </div>
            <div data-tabpanel="mkdir" hidden>
              <div class="form-row">
                <div class="upfield">
                  <mdui-text-field name="mkdir-name" label="資料夾名稱"></mdui-text-field>
                </div>
                <mdui-button data-create-folder icon="create_new_folder">建立</mdui-button>
              </div>
              <div data-upload-result></div>
            </div>"""
