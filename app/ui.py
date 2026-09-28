"""MDUI v2 HTML shell + reusable page components (zh-TW or English).

Every user-facing route renders through :func:`page` so the whole site shares
one Material Design 3 look (MDUI v2 via CDN, auto dark mode). Language follows
the client IP (Traditional Chinese for Taiwan, English elsewhere) — see
:mod:`app.i18n`. API clients never see this; they get JSON/text via content
negotiation.
"""

from __future__ import annotations

import datetime
import html

from .i18n import EN, ZH, other, t

MDUI_CSS = "https://unpkg.com/mdui@2/mdui.css"
MDUI_JS = "https://unpkg.com/mdui@2/mdui.global.js"
ICON_FONT = "https://fonts.googleapis.com/icon?family=Material+Icons"


def nav_items(lang: str, active: str, authed: bool) -> list[tuple[str, str, str, str]]:
    items = [
        ("home", t(lang, "nav_home"), "/", "home"),
        ("api", t(lang, "nav_api"), "/api", "api"),
        ("docs", t(lang, "nav_docs"), "/docs", "menu_book"),
    ]
    if authed:
        # Private mode: no public upload entry after login.
        items.append(("logout", t(lang, "nav_logout"), "/logout", "logout"))
    else:
        items.insert(1, ("upload", t(lang, "nav_upload"), "/upload", "upload"))
        items.append(("login", t(lang, "nav_login"), "/login", "login"))
    return items


def legal_footer(lang: str, extra_qs: str = "") -> str:
    """Bottom-of-page rules line + links, including the legal page (catbox style).

    `extra_qs` keeps the current view (e.g. the open folder) when the reader
    switches language.
    """
    rules = (
        "僅限合法用途；公開檔案任何人可下載，違規內容直接刪除。"
        if lang == ZH
        else "Lawful use only: public files can be downloaded by anyone, offending content is removed."
    )
    legal = "法律條款 Legal" if lang == ZH else "Legal"
    limits = "限制 Limits" if lang == ZH else "Limits"
    return (
        '<footer class="legalbar">'
        f'<span class="tos-short">{html.escape(rules)}</span>'
        '<span class="legal-links">'
        f'<a href="/legal">{html.escape(legal)}</a>'
        f'<a href="/docs/limits">{html.escape(limits)}</a>'
        '<a href="/llms.txt">llms.txt</a>'
        f'<a href="?{html.escape(extra_qs)}lang={other(lang)}" title="切換語言 / switch language">'
        f'{html.escape(t(lang, "lang_zh"))}</a>'
        "</span></footer>"
    )


def page(
    title: str,
    body: str,
    active: str = "home",
    extra_head: str = "",
    authed: bool = False,
    lang: str = EN,
    extra_qs: str = "",
) -> str:
    nav_html = []
    for key, label, href, icon in nav_items(lang, active, authed):
        cls = "mdui-list-item-active" if key == active else ""
        nav_html.append(
            f'<mdui-list-item href="{href}" class="{cls}" rounded>'
            f"{html.escape(label)}"
            f'<mdui-icon slot="icon" name="{icon}"></mdui-icon>'
            "</mdui-list-item>"
        )
    return f"""<!DOCTYPE html>
<html lang="{html.escape(lang)}" class="mdui-theme-auto" data-lang="{html.escape(lang)}">
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
      <div class="nav-foot">{html.escape(t(lang, "nav_foot"))}</div>
    </div>
  </mdui-navigation-drawer>
  <mdui-layout-main>
    <main class="page" data-droproot>
      {body}
      {legal_footer(lang, extra_qs)}
      <div class="drophint" data-drophint hidden>{html.escape(t(lang, "drop_hint"))}</div>
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


def limits_note(lang: str) -> str:
    from .config import settings

    return '<p class="muted limits-first">' + html.escape(
        t(
            lang,
            "limits",
            gb=settings.max_file_size // 1024**3,
            mins=settings.bw_window_seconds // 60,
            fgb=settings.bw_folder_hard_bytes // 1024**3,
        )
    ) + "</p>"


def thread_panel(lang: str) -> str:
    """IDM-style upload monitor: overall bar + segment map + 16 thread rows."""
    return f"""<div class="tp" data-tp hidden>
      <div class="tp-top">
        <strong data-tp-pct>0%</strong>
        <span data-tp-speed class="tpspeed"></span>
        <span data-tp-note class="tp-note"></span>
      </div>
      <mdui-linear-progress data-tp-bar></mdui-linear-progress>
      <div class="tp-seglabel muted">{html.escape(t(lang, "tp_chunks", chunks=""))}<span data-tp-segcount></span></div>
      <div class="segbar" data-tp-segs></div>
      <table class="tptable">
        <thead><tr><th>No</th><th>{html.escape(t(lang, "tp_idle"))}</th></tr></thead>
        <tbody data-tp-rows></tbody>
      </table>
      <div class="form-row">
        <mdui-button variant="outlined" data-tp-pause>{html.escape(t(lang, "tp_pause"))}</mdui-button>
      </div>
    </div>"""


def endpoint_card(lang: str, method: str, path: str, desc: str, href: str | None = None) -> str:
    link = (
        f'<a href="{html.escape(href)}"><mdui-button variant="text">'
        f'{html.escape(t(lang, "btn_open"))}</mdui-button></a>'
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
    """`652 B · content type · 2026-09-28 16:58 · free-text description`."""
    bits = [fmt_size(f.get("bytes", f.get("size", 0)) if "bytes" in f else f.get("size", 0))]
    if with_type and f.get("content_type"):
        bits.append(str(f["content_type"]))
    bits.append(fmt_time(f.get("ctime", 0)))
    desc = str(f.get("description", "") or "")
    if desc:
        bits.append(desc)
    return " · ".join(html.escape(b) for b in bits if b)


def _row_buttons(lang: str, f: dict, dl: str, pv: str, copy_label: str) -> str:
    size = f.get("size", 0)
    return (
        f'<mdui-button-icon slot="end-icon" icon="visibility" data-preview="{html.escape(pv)}"'
        f' data-name="{html.escape(f["name"])}" title="{html.escape(t(lang, "btn_preview"))}"></mdui-button-icon>'
        f'<mdui-button-icon slot="end-icon" icon="download" data-mt-download="{html.escape(dl)}"'
        f' data-name="{html.escape(f["name"])}" data-size="{size}"'
        f' title="{html.escape(t(lang, "btn_download"))}"></mdui-button-icon>'
        f'<mdui-button slot="end-icon" variant="text" data-copy="{html.escape(dl)}">'
        f"{html.escape(copy_label)}</mdui-button>"
    )


def file_rows(lang: str, files: list[dict], folder_id: str, base: str) -> str:
    """Public folder file list: preview + download + copy (one download path)."""
    if not files:
        return f'<mdui-card variant="filled" class="empty">{html.escape(t(lang, "empty_folder"))}</mdui-card>'
    rows = []
    for f in files:
        dl = f.get("download_url") or f"{base}/dl/pub/{folder_id}/{f['id']}"
        preview = f"{dl}?preview=1"
        copy_target = f.get("short_url") or dl
        rows.append(
            "<mdui-list-item>"
            '<mdui-icon slot="icon" name="description"></mdui-icon>'
            f'<div><div class="fname">{html.escape(f["name"])}</div>'
            f'<div class="fmeta">{_meta_line(f)}</div></div>'
            + _row_buttons(lang, f, copy_target, preview, t(lang, "btn_copy_link"))
            + "</mdui-list-item>"
        )
    return f'<mdui-list class="file-list">{"".join(rows)}</mdui-list>'


def _drop_attrs(scope: str, folder_id: str = "", label: str = "") -> str:
    """Marks a card as a drop target: scope + target folder id ("" = uncategorised)."""
    return (
        f'data-dropscope="{html.escape(scope)}" data-dropfolder="{html.escape(folder_id)}"'
        + (f' data-droplabel="{html.escape(label)}"' if label else "")
    )


def private_file_rows(lang: str, files: list[dict], base: str, scope: str = "private") -> str:
    """File list: preview + download + copy + rename + delete, draggable between folders.

    Set `dl` on an entry to override the download path (public files live under
    /dl/pub/<folder>/ or /dl/s/, private ones under /dl/), and `rename_post` to
    `0` / `1` to mark it as a public file for the rename endpoint.
    """
    if not files:
        return f'<mdui-card variant="filled" class="empty">{html.escape(t(lang, "empty_files"))}</mdui-card>'
    rows = []
    for f in files:
        dl = f.get("dl") or f"{base}/dl/{f['id']}"
        pv = f"{base}/view/{f['id']}" if scope == "private" else f"{dl}?preview=1"
        del_url = f.get("delete_url") or (base + "/del/" + f["id"])
        post = ' data-delete-post="1"' if f.get("delete_post") else ""
        rename = (
            f'<mdui-button-icon slot="end-icon" icon="edit" data-rename-file="{html.escape(f["id"])}"'
            f' data-name="{html.escape(f["name"])}" data-public="{f.get("rename_post", 0)}"'
            f' data-in-folder="{html.escape(f.get("folder_id", "") or "")}"'
            f' title="{html.escape(t(lang, "btn_rename"))}"></mdui-button-icon>'
        )
        rows.append(
            "<mdui-list-item"
            f' draggable="true" data-move="{html.escape(f["id"])}" data-scope="{html.escape(scope)}"'
            f' data-from="{html.escape(f.get("folder_id", "") or "")}"'
            f' data-name="{html.escape(f["name"])}"'
            f' data-sort-name="{html.escape(f["name"].lower())}"'
            f' data-sort-size="{int(f.get("bytes", f.get("size", 0)))}"'
            f' data-sort-time="{float(f.get("ctime", 0))}"'
            ">"
            '<mdui-icon slot="icon" name="description"></mdui-icon>'
            f'<div><div class="fname">{html.escape(f["name"])}</div>'
            f'<div class="fmeta">{_meta_line(f, with_type=False)}</div></div>'
            + _row_buttons(lang, f, dl, pv, t(lang, "btn_direct_link"))
            + rename
            + f'<mdui-button slot="end-icon" variant="text" data-delete="{html.escape(del_url)}"'
            + post
            + f' data-name="{html.escape(f["name"])}">{html.escape(t(lang, "btn_delete"))}</mdui-button>'
            "</mdui-list-item>"
        )
    return f'<mdui-list class="file-list">{"".join(rows)}</mdui-list>'


def sort_bar(lang: str) -> str:
    return f"""<div class="sortbar" data-sortbar data-dir="desc" data-by="time">
      <span class="muted">{html.escape(t(lang, "sort_by"))}</span>
      <mdui-button variant="filled" data-sort-by="time">{html.escape(t(lang, "sort_time"))}</mdui-button>
      <mdui-button variant="text" data-sort-by="size">{html.escape(t(lang, "sort_size"))}</mdui-button>
      <mdui-button variant="text" data-sort-by="name">{html.escape(t(lang, "sort_name"))}</mdui-button>
      <mdui-button-icon data-sort-dir icon="arrow_downward"></mdui-button-icon>
    </div>"""


def share_file_rows(lang: str, files: list[dict], token: str, base: str) -> str:
    """Shared folder rows: preview + download + copy, no delete."""
    if not files:
        return f'<mdui-card variant="filled" class="empty">{html.escape(t(lang, "empty_folder"))}</mdui-card>'
    rows = []
    for f in files:
        dl = f"{base}/dl/sh/{token}/{f['id']}"
        rows.append(
            "<mdui-list-item>"
            '<mdui-icon slot="icon" name="description"></mdui-icon>'
            f'<div><div class="fname">{html.escape(f["name"])}</div>'
            f'<div class="fmeta">{_meta_line(f, with_type=False)}</div></div>'
            + _row_buttons(lang, f, dl, f"{dl}?preview=1", t(lang, "btn_copy_link"))
            + "</mdui-list-item>"
        )
    return f'<mdui-list class="file-list">{"".join(rows)}</mdui-list>'


def _private_upload_form(lang: str, folder_id: str = "") -> str:
    """The uploader that lives in the Drive toolbar. No card, no visible button:
    the toolbar's Upload button opens the file picker on this input."""
    return f"""
          <form class="drive-upload" action="/api/upload_chunk" method="post"
                data-chunked data-merge="/api/merge_chunks">
            <input type="file" name="file" multiple required class="visually-hidden">
            <input type="hidden" name="folder_id" value="{html.escape(folder_id)}">
            {thread_panel(lang)}
            <div data-upload-result></div>
          </form>"""


def _share_rows(lang: str, fid: str, base: str, shares: dict) -> str:
    rows = "".join(
        f'<div class="rlink"><span class="rlink-label">'
        f'{html.escape(t(lang, "share_view_only" if s.get("mode") == "view" else "share_can_upload"))}</span>'
        f"<code>{html.escape(base + '/s/' + tok)}</code>"
        '<span class="rlink-btns">'
        f'<mdui-button variant="text" data-copy="{html.escape(base + "/s/" + tok)}">'
        f'{html.escape(t(lang, "btn_copy"))}</mdui-button>'
        f'<mdui-button variant="text" data-unshare="{html.escape(tok)}">'
        f'{html.escape(t(lang, "btn_cancel"))}</mdui-button>'
        "</span></div>"
        for tok, s in shares.items()
        if s.get("folder_id") == fid
    )
    return f'<div class="sharebox">{rows}</div>' if rows else ""


def folder_tile(lang: str, fid: str, name: str, count: int, base: str, shares: dict) -> str:
    """One folder in the Drive grid: open it, rename it, share it, delete it.

    Also a drop target: a file row dragged here moves in, files dragged from the
    desktop upload straight into it.
    """
    return f"""
        <div class="ftile" {_drop_attrs("private", fid, name)}>
          <a class="ftile-open" href="/?folder={html.escape(fid)}">
            <mdui-icon name="folder" class="ftile-icon"></mdui-icon>
            <span class="ftile-name">{html.escape(name)}</span>
            <span class="ftile-sub">{html.escape(t(lang, "drive_items", n=count))}</span>
          </a>
          <span class="ftile-btns">
            <mdui-button-icon icon="edit" data-rename="{html.escape(fid)}" data-name="{html.escape(name)}"
              data-public="0" title="{html.escape(t(lang, "btn_rename"))}"></mdui-button-icon>
            <mdui-button-icon icon="link" data-share-create="{html.escape(fid)}" data-mode="view"
              title="{html.escape(t(lang, "share_view_link"))}"></mdui-button-icon>
            <mdui-button-icon icon="delete" data-delete-dir="{html.escape(base + "/deldir/" + fid)}"
              data-name="{html.escape(name)}" data-count="{count}"
              title="{html.escape(t(lang, "btn_delete"))}"></mdui-button-icon>
          </span>
          {_share_rows(lang, fid, base, shares)}
        </div>"""


def public_folder_tile(lang: str, f: dict, base: str) -> str:
    url = base + "/f/" + f["id"]
    return f"""
        <div class="ftile" {_drop_attrs("public", f["id"], f["name"])}>
          <a class="ftile-open" href="{html.escape(url)}">
            <mdui-icon name="folder" class="ftile-icon"></mdui-icon>
            <span class="ftile-name">{html.escape(f["name"])}</span>
            <span class="ftile-sub">{html.escape(t(lang, "drive_items", n=f["count"]))}</span>
          </a>
          <span class="ftile-btns">
            <mdui-button-icon icon="open_in_new" data-copy="{html.escape(url)}"
              title="{html.escape(t(lang, "btn_copy_link"))}"></mdui-button-icon>
            <mdui-button-icon icon="edit" data-rename="{html.escape(f["id"])}" data-name="{html.escape(f["name"])}"
              data-public="1" title="{html.escape(t(lang, "btn_rename"))}"></mdui-button-icon>
            <mdui-button-icon icon="delete" data-delpubdir="{html.escape(base + "/delpubdir/" + f["id"])}"
              data-name="{html.escape(f["name"])}" data-count="{f["count"]}"
              title="{html.escape(t(lang, "btn_delete"))}"></mdui-button-icon>
          </span>
        </div>"""


def _drive_toolbar(lang: str, base: str, cur: str, cur_name: str) -> str:
    """Breadcrumb + New folder + Upload. Doubles as the current-folder drop zone."""
    crumb = f'<a class="crumb" href="/" {_drop_attrs("private", "", t(lang, "drive_title"))}>{html.escape(t(lang, "drive_title"))}</a>'
    if cur:
        crumb += (
            f'<span class="crumb-sep">/</span><span class="crumb-now">'
            f'{html.escape(cur_name)}</span>'
        )
    return f"""
        <mdui-card variant="outlined" class="card-pad drivebar" {_drop_attrs("private", cur, cur_name or t(lang, "drive_title"))}>
          <div class="drivebar-top">
            <nav class="crumbs">{crumb}</nav>
            <div class="form-row">
              <mdui-button-icon icon="create_new_folder" data-new-folder
                title="{html.escape(t(lang, "drive_new_folder"))}"></mdui-button-icon>
              <mdui-button-icon icon="cloud_upload" data-drive-upload
                title="{html.escape(t(lang, "btn_upload"))}"></mdui-button-icon>
            </div>
          </div>
          <p class="muted drive-hint">{html.escape(t(lang, "drive_hint"))}</p>
        </mdui-card>"""


def drive_panel(
    lang: str,
    files: list[dict],
    base: str,
    folders: dict,
    shares: dict,
    current: str = "",
    public: list[dict] | None = None,
    public_folders: list[dict] | None = None,
) -> str:
    """Admin home: the private drive (Google Drive style) plus the public area.

    Inside a folder the list shows that folder's files; at the root it shows the
    uncategorised ones. All folders stay visible as tiles and are drop targets,
    so a file can be dragged into any of them from anywhere.
    """
    public = public or []
    public_folders = public_folders or []
    cur_name = (folders.get(current) or {}).get("name", "") if current else ""
    shown = [f for f in files if (f.get("folder") or "") == (current or "")]
    for f in files:  # POST the delete so the drive stays on the folder it shows
        f["delete_post"] = True
    for f in public:  # public files carry their own download path
        f["bytes"] = f.get("size", 0)
        f["dl"] = (
            f"{base}/dl/pub/{f['folder_id']}/{f['id']}" if f.get("folder_id") else f"{base}/dl/s/{f['id']}"
        )
        f["delete_url"] = f"{base}/delpub/{f['id']}"
        f["delete_post"] = True
        f["rename_post"] = 1

    counts: dict[str, int] = {}
    for f in files:
        if f.get("folder"):
            counts[f["folder"]] = counts.get(f["folder"], 0) + 1
    # the folder you are inside is not in its own listing, like Drive
    tiles = "".join(
        folder_tile(lang, fid, m.get("name") or t(lang, "unnamed_folder"), counts.get(fid, 0), base, shares)
        for fid, m in folders.items()
        if fid != current
    )
    no_folders = f'<mdui-card variant="filled" class="empty">{html.escape(t(lang, "drive_no_folders"))}</mdui-card>'
    pub_tiles = "".join(public_folder_tile(lang, f, base) for f in public_folders)
    n_pub = len(public)
    return f"""
        <div class="drive" data-drive>
        <mdui-tabs value="drive" data-tabs>
          <mdui-tab value="drive">{html.escape(t(lang, "drive_title"))}</mdui-tab>
          <mdui-tab value="public">{html.escape(t(lang, "tab_public", n=n_pub))}</mdui-tab>
        </mdui-tabs>

        <div data-tabpanel="drive">
          {_drive_toolbar(lang, base, current, cur_name)}
          {_private_upload_form(lang, current)}
          <div class="tiles">{tiles}</div>
          {no_folders if not tiles else ""}
          <mdui-card variant="outlined" class="card-pad"
            {_drop_attrs("private", current, cur_name or t(lang, "drive_title"))}>
            <h2>{html.escape(t(lang, "drive_files_h", n=len(shown), name=cur_name or t(lang, "drive_title")))}</h2>
            {sort_bar(lang)}
            {private_file_rows(lang, shown, base)}
          </mdui-card>
        </div>

        <div data-tabpanel="public" hidden>
          {public_upload_form(lang=lang)}
          <mdui-card variant="outlined" class="card-pad">
            <h2>{html.escape(t(lang, "public_folders_h", n=len(public_folders)))}</h2>
            <div class="tiles">{pub_tiles}</div>
            {no_folders if not pub_tiles else ""}
          </mdui-card>
          <mdui-card variant="outlined" class="card-pad">
            <h2>{html.escape(t(lang, "public_files_h", n=n_pub))}</h2>
            {sort_bar(lang)}
            {private_file_rows(lang, public, base, scope="public")}
          </mdui-card>
        </div>
        </div>"""


def _upload_row(lang: str, folder: str | None = None) -> str:
    """File picker row + optional folder/description fields, one per line."""
    if folder:
        field = f'<input type="hidden" name="folder" value="{html.escape(folder)}">'
    else:
        field = (
            '<div class="upfield">'
            f'<mdui-text-field name="folder" label="{html.escape(t(lang, "folder_field"))}"></mdui-text-field>'
            "</div>"
        )
    label = t(lang, "btn_add_folder") if folder else t(lang, "btn_upload")
    return f"""
              <div class="form-row">
                <input type="file" name="file" multiple required>
                <mdui-button type="submit" icon="cloud_upload">{html.escape(label)}</mdui-button>
              </div>
              {field}
              <div class="upfield">
                <mdui-text-field name="description" label="{html.escape(t(lang, "desc_field"))}"></mdui-text-field>
              </div>"""


def public_upload_form(lang: str, folder_id: str | None = None) -> str:
    """Public upload UI. Folder page: join-only form. Else: upload/create tabs."""
    form = f"""
            {limits_note(lang)}
            <form action="/api/public/chunk" method="post" data-chunked data-merge="/api/public/merge_chunks" data-public="1">
              {_upload_row(lang, folder_id)}
              {thread_panel(lang)}
            </form>
            <div data-upload-result></div>"""
    if folder_id:
        return form
    return f"""
            <mdui-tabs value="up" data-tabs>
              <mdui-tab value="up">{html.escape(t(lang, "tab_upload"))}</mdui-tab>
              <mdui-tab value="mkdir">{html.escape(t(lang, "tab_mkdir"))}</mdui-tab>
            </mdui-tabs>
            <div data-tabpanel="up">
              {form}
            </div>
            <div data-tabpanel="mkdir" hidden>
              <div class="form-row">
                <div class="upfield">
                  <mdui-text-field name="mkdir-name" label="{html.escape(t(lang, "folder_name_field"))}"></mdui-text-field>
                </div>
                <mdui-button data-create-folder icon="create_new_folder">{html.escape(t(lang, "btn_create_folder"))}</mdui-button>
              </div>
              <div data-upload-result></div>
            </div>"""
