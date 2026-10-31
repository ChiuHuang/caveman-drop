"""API index + machine-readable docs (llms.txt)."""

from __future__ import annotations

import html

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from ..config import settings
from ..negotiation import wants_html
from ..i18n import lang_for, t
from ..ui import endpoint_card, page
from ..urls import base_url

router = APIRouter()


def _api_payload(request: Request) -> dict:
    base = base_url(request)
    return {
        "name": "CaveMan Drop public API",
        "description": "Anonymous file sharing. Upload a file, get a permanent share link back. No auth required. file_id is the sha256 of the content, so identical files are stored once.",
        "language": (
            "Browser UI language is decided by the browser: an inline page script reads "
            "navigator.languages, stores the pick in a lang cookie and reloads once "
            "(zh-TW for Traditional-Chinese browsers, English otherwise). Force it with "
            "?lang=zh-TW or ?lang=en. JSON and text output is always English."
        ),
        "storage": {
            "file_id": "sha256 hex of the file bytes (same content = same id and link)",
            "blob_store": "bytes are stored once under BIN_DIR (default bin/); re-uploading an identical file reuses that copy",
            "deduplicated": "true in an upload response when the bytes were already stored",
        },
        "description": (
            "Optional free-text note. multipart uploads take a `description` form field; "
            "merge_chunks takes a `description` JSON key. Echoed back in every response "
            "and shown in listings."
        ),
        "limits": {
            "max_file_size_bytes": settings.max_file_size,
            "max_file_size_human": f"{settings.max_file_size // 1024**3} GB (public uploads; private uncapped)",
            "folder_window_cap_human": (
                f"{settings.bw_folder_hard_bytes // 1024**3} GB per "
                f"{settings.bw_window_seconds // 60} min per folder (bandwidth window, not storage total)"
            ),
            "rate_limit": (
                f"{settings.rate_limit_max_uploads} uploads / IP / "
                f"{settings.rate_limit_window // 60} min"
            ),
        },
        "endpoints": {
            "create_folder": {
                "method": "POST",
                "url": f"{base}/api/public/folder",
                "notes": "Creates an empty public folder and returns share/upload URLs. Optional JSON body {name}.",
            },
            "upload": {
                "method": "POST",
                "url": f"{base}/api/public/upload",
                "form_fields": {
                    "file": "the file to upload (required)",
                    "folder": "existing folder_id to add this file to, or free text to create a new folder with that name (optional — omitted means a single direct file, no folder is created)",
                },
                "example_curl": f'curl -F "file=@myfile.txt" {base}/api/public/upload',
            },
            "upload_chunked": {
                "method": "POST",
                "chunk_url": f"{base}/api/public/chunk",
                "merge_url": f"{base}/api/public/merge_chunks",
                "notes": "Chunked public upload. POST parts (multipart: file_chunk, upload_id, index, filename) in parallel, then POST JSON {upload_id, filename, total_chunks, folder?} to merge.",
            },
            "list_folder": {
                "method": "GET",
                "url": f"{base}/api/public/folder/{{folder_id}}",
            },
            "file_metadata": {
                "method": "GET",
                "url": f"{base}/api/public/file/{{folder_id}}/{{file_id}}",
            },
            "download": {
                "method": "GET",
                "url": f"{base}/dl/pub/{{folder_id}}/{{file_id}}",
                "notes": "Supports HTTP Range requests for resumable/parallel downloads.",
            },
            "single_metadata": {
                "method": "GET",
                "url": f"{base}/api/public/single/{{file_id}}",
            },
            "single_download": {
                "method": "GET",
                "url": f"{base}/dl/s/{{file_id}}",
                "notes": "Direct download for folderless single files. Range supported; ?preview=1 previews inline.",
            },
            "short_download": {
                "method": "GET",
                "url": f"{base}/{{code}}.{{ext}}",
                "notes": (
                    "catbox-style short link at the root: the shortest unique prefix of the "
                    "file's sha256, 6 characters (7, 8 … when a different file shares those "
                    "characters). Immutable Cache-Control, so a CDN in front can cache it. "
                    "Public files only. Returned as `short_url` by every upload and listing "
                    "response. In the default deployment the host is USERCONTENT_HOST "
                    "(usercontent.qiuhuang.dev), not this one — so a link reads "
                    "https://usercontent.qiuhuang.dev/<code>.<ext>. The /usercontent/<code>.<ext> "
                    "path still works as an alias for links handed out earlier."
                ),
            },
            "upload_from_url": {
                "method": "POST",
                "url": f"{base}/api/public/upload_url",
                "body": {"url": "https://example.com/file.jpg", "folder": "<id or new name (optional)>", "description": "(optional)"},
                "notes": (
                    "Server-side fetch: the server downloads the URL through PROXY_BASE_URL and "
                    "files it like an ordinary public upload (same folder field rules). "
                    "Anonymous callers are capped at URL_THROTTLE_MBPS (default 60 Mbps); "
                    "a signed-in session is uncapped. Same JSON response as /api/public/upload."
                ),
            },
            "folder_zip": {
                "method": "GET",
                "url": f"{base}/zip/f/{{folder_id}}",
                "notes": (
                    "Download an entire public folder as one .zip, streamed live — the archive "
                    "is built in memory step by step and never written to disk. Files without "
                    "subdirectories; duplicate names get a ' (1)' style suffix."
                ),
            },
            "folder_zip_private": {
                "method": "GET",
                "url": f"{base}/zip/{{folder_id}}",
                "notes": "Same as /zip/f/{{folder_id}} but for a private drive folder; needs a signed-in session.",
            },
            "upload_page": {
                "method": "GET",
                "url": f"{base}/upload",
                "notes": "Human-friendly anonymous upload page that returns a file URL and share URL.",
            },
            "ai_docs": {
                "method": "GET",
                "url": f"{base}/api/llms.txt",
            },
            "speed_probe": {
                "method": "POST",
                "url": f"{base}/api/public/probe",
                "notes": (
                    "Optional diagnostic for scripts: POST a blob to get a thread count and "
                    "the measured Mbps. Optional `ms` field with your own duration. The "
                    "browser does not use it — it adapts from the first chunks it uploads."
                ),
            },
            "browse_page": {
                "method": "GET",
                "url": f"{base}/f/{{folder_id}}",
                "notes": "Human-friendly page for browsing/downloading/uploading to a folder — share this link with others.",
            },
            "rename_folder_admin": {
                "method": "POST",
                "url": f"{base}/api/public/folder/rename",
                "body": {"folder_id": "<uuid>", "name": "new display name"},
                "notes": (
                    "Admin only (password session, ?auth= or ?token=) — or the browser "
                    "session that created the folder. Changes a public folder's display "
                    "name. The folder_id and every existing link keep working."
                ),
            },
            "folder_perm": {
                "method": "POST",
                "url": f"{base}/api/public/folder/perm",
                "body": {"folder_id": "<uuid>", "perm": "readonly | upload | both"},
                "notes": (
                    "Set what non-owners may do with a public folder: readonly (list + "
                    "download), upload (dropbox), or both (default). Admin, or the "
                    "session that created the folder. POST /api/public/folder accepts "
                    "`perm` at creation, and assigns the folder to the creating session."
                ),
            },
            "private_drive": {
                "method": "GET",
                "url": f"{base}/?folder={{folder_id}}",
                "notes": (
                    "Signed-in drive view: folder tiles, breadcrumb, file list. Admin only. "
                    "GET / with no folder lists the uncategorised files."
                ),
            },
            "rename_private_folder_admin": {
                "method": "POST",
                "url": f"{base}/api/folders/rename",
                "body": {"folder_id": "<uuid>", "name": "new display name"},
                "notes": "Admin only. Changes a private folder's name; id, files and share links stay.",
            },
            "folder_perm_private": {
                "method": "POST",
                "url": f"{base}/api/folders/perm",
                "body": {"folder_id": "<uuid>", "perm": "view | upload | both"},
                "notes": (
                    "Admin only. A private folder's default share-link mode. POST "
                    "/api/folders accepts `perm` at creation; POST /api/folders/{id}/share "
                    "takes an optional mode (view / upload / both) — defaulting to the "
                    "folder's — and returns the /s/{token} link. view = list + download, "
                    "upload = dropbox, both = everything."
                ),
            },
        },
    }


@router.get("/api")
async def api_root(request: Request):
    if wants_html(request):
        lang = lang_for(request)
        zh = lang == "zh-TW"
        cards = [
            ("POST", "/api/public/upload", "匿名上傳 — multipart 欄位 'file'，選填 'folder'。", "/upload"),
            ("POST", "/api/public/chunk → /api/public/merge_chunks", "分段上傳：先傳分塊再合併，大檔案自動使用。", "/upload"),
            ("POST", "/api/public/folder", "建立空資料夾，回傳分享與上傳網址。", "/upload"),
            ("GET", "/api/public/folder/{folder_id}", "資料夾資訊、檔案清單與下載網址。", None),
            ("GET", "/api/public/file/{folder_id}/{file_id}", "單一檔案資訊與下載網址。", None),
            ("GET", "/dl/pub/{folder_id}/{file_id}", "下載檔案本體。支援 Range 續傳 / 並行。", None),
            ("GET", "/{code}.{ext}", "短網址：sha256 前綴，immutable，可進 CDN。", None),
            ("GET", "/api/files", "私人檔案清單（需密碼登入）。", "/login"),
            ("POST", "/api/upload_chunk + /api/merge_chunks", "私人分段上傳（登入後不限速）。", "/login"),
        ]
        en_cards = [
            ("POST", "/api/public/upload", "Anonymous upload: multipart field 'file', optional 'folder'.", "/upload"),
            ("POST", "/api/public/chunk → /api/public/merge_chunks", "Chunked upload, automatic for large files.", "/upload"),
            ("POST", "/api/public/folder", "Create an empty public folder, get share and upload URLs.", "/upload"),
            ("GET", "/api/public/folder/{folder_id}", "Folder metadata, file list and download URLs.", None),
            ("GET", "/api/public/file/{folder_id}/{file_id}", "Single file metadata and download URL.", None),
            ("GET", "/dl/pub/{folder_id}/{file_id}", "Download bytes. Supports Range for resume/parallel.", None),
            ("GET", "/{code}.{ext}", "Short link: sha256 prefix, immutable, CDN friendly.", None),
            ("GET", "/api/files", "Private file list (password required).", "/login"),
            ("POST", "/api/upload_chunk + /api/merge_chunks", "Private chunked upload (unthrottled when signed in).", "/login"),
        ]
        rows = (cards if zh else en_cards)
        body = f"""<mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(t(lang, "api_index_h"))}</h1>
          <p>{html.escape(t(lang, "api_index_p"))}</p>
          <div class="form-row">
            <a href="/llms.txt"><mdui-button variant="outlined">{html.escape(t(lang, "ai_docs"))}</mdui-button></a>
            <a href="/docs/api"><mdui-button variant="text">{html.escape(t(lang, "full_ref"))}</mdui-button></a>
          </div>
        </mdui-card>
        <div class="stack">
        {"".join(endpoint_card(lang, m, pth, d, h) for m, pth, d, h in rows)}
        </div>"""
        return HTMLResponse(page(t(lang, "api_h"), body, active="api", lang=lang))
    return _api_payload(request)


LLMS_TEMPLATE = """# CaveMan Drop Public File API

This is an anonymous public file-sharing API. No authentication is required.
CORS is enabled for browser JavaScript and AI agents.

## Upload a file
POST {base}/api/public/upload
Content-Type: multipart/form-data
Fields:
- file: required file
- folder: optional existing folder_id, or free text to name a new folder
  (adds to that folder; omit it entirely for a single direct file — no
  folder is created)
Returns JSON containing `url` and `download_url` (plus `folder_url` etc.
only when a folder was used).

`file_id` is the sha256 of the uploaded bytes, so the same content always
yields the same id and the same link. Identical bytes are stored once in
the bin directory — re-uploading does not store a second copy and returns
`"deduplicated": true`.

An optional free-text `description` may be sent with the upload
(multipart field `description`, or a `description` key in the merge JSON);
it is echoed back and shown in listings.

## Short share links
GET {base}/{{code}}.{{ext}}
`code` is the shortest unique prefix of the file's sha256: 6 characters, or
7, 8 … if another file starts with the same characters. Served with an
immutable `Cache-Control`, so a CDN can hold it. Public files only.
Every response also carries it as `short_url`. `/usercontent/{{code}}.{{ext}}`
still works as an alias for links handed out earlier.

Generated links follow the request: an HTTPS request gets HTTPS URLs back
(`Forwarded` / `X-Forwarded-Proto` are honoured).

## Private access without a cookie
Private endpoints accept `?auth=<PASSWORD>` in the query string, for clients
that go through a CORS-style proxy (`https://proxy.example/https://this.host/…`):
the proxy forwards the request but the browser never receives our Set-Cookie,
so a cookie session cannot work. Pass the parameter on every request instead.
Honoured over HTTPS only, never echoed into a response or redirect
(`/login?auth=…` redirects to `/` and drops it), and 10 wrong guesses from one
IP lock it out for 10 minutes. `?token=<mobile token>` also works as before.

## Private-only hosts
`PRIVATE_ONLY_HOSTS` (default `pvf.chiuhuang.dev`) lists the domains that serve
the private drive alone. There `/` is the login page when signed out and the
drive on its own when signed in — no tabs, no public UI — and `/upload` redirects
to `/`. The public JSON API keeps working on those hosts, so scripts are
unaffected.

## Create an empty public folder
POST {base}/api/public/folder
JSON `{{"name": "free text", "perm": "readonly" | "upload" | "both" (both by
default)}}`. Returns a folder_id plus `folder_url`, `upload_url`, and
`folder_api_url`. A browser session becomes the folder's owner: it can rename
(POST /api/public/folder/rename), delete (POST /delpubdir/{{folder_id}}), or
re-permission (POST /api/public/folder/perm) without logging in. Non-owners
follow `perm`: readonly = list + download only, upload = dropbox only,
both = everything (the old behaviour).

## Private folders and share links
POST {base}/api/folders (JSON `name`, optional `perm`: view / upload / both) —
the folder's default share mode. POST /api/folders/{{id}}/share (optional
`mode`, defaulting to that perm) returns a /s/{{token}} link: view links list
and download, upload links only accept files, both do everything. Requires a
signed-in session.

## Chunked upload (browsers + scripts)
POST {base}/api/public/chunk (multipart: `file_chunk`, `upload_id` (uuid),
`index` (0-based), `filename`) — send parts in parallel, then
POST {base}/api/public/merge_chunks (JSON: `upload_id`, `filename`,
`total_chunks`, optional `folder`, optional `description`) to assemble.
Returns the same payload as the single-POST upload. The browser starts with
16 parts in flight and adapts the count from the throughput of the first few
parts (byte-level upload progress, not latency), so slow links go to 32/64/128.
Scripts that want a recommendation can POST {base}/api/public/probe, optionally
with an `ms` field carrying their own measured duration.

## Single direct files
GET {base}/api/public/single/{{file_id}} — metadata + direct URL.
GET {base}/dl/s/{{file_id}} — download (?preview=1 previews inline).

## List a folder
GET {base}/api/public/folder/{{folder_id}}
Returns files and direct download URLs.

## Get file metadata
GET {base}/api/public/file/{{folder_id}}/{{file_id}}

## Download
GET {base}/dl/pub/{{folder_id}}/{{file_id}}
Supports HTTP Range requests.

## Download a whole folder as .zip
GET {base}/zip/f/{{folder_id}}          (public folder)
GET {base}/zip/{{folder_id}}            (private folder, signed-in only)
Streamed live; the archive is built in memory and never written to disk.

## Upload from a URL (server-side fetch)
POST {base}/api/public/upload_url
JSON: {{"url": "https://example.com/file.jpg", "folder": "<id or new name (optional)>", "description": "(optional)"}}
The server fetches the URL through its proxy and files the bytes like an
ordinary public upload (same `folder` rules and response shape). Anonymous
calls are throttled to 60 Mbps by default; a signed-in session is uncapped.

## Human upload/share page
GET {base}/upload
GET {base}/f/{{folder_id}}

## Admin: rename a folder
POST {base}/api/public/folder/rename
JSON: {{"folder_id": "<uuid>", "name": "new display name"}}
Admin only (password session, `?auth=`, or `?token=`). Only the display name
changes — the folder id, its share URL and every file link keep working.
POST {base}/api/folders/rename does the same for a private folder.

## Admin: the private drive
GET {base}/?folder={{folder_id}}
Signed-in view: folder tiles (each one a drop target), a breadcrumb, and the
file list of the folder being viewed. Without `folder` it lists the
uncategorised files. Dragging a file row onto a folder tile moves it there;
dragging files from the desktop uploads them into the tile. Renames, new
folders, sharing and deletes all happen from the tiles, and
POST /del/{{file_id}} and /deldir/{{folder_id}} accept POST as well as GET so
the page does not have to navigate away.

## Full docs
GET {base}/docs (HTML for browsers, Markdown for agents via ?format=text)
GET {base}/api (JSON index)

## Limits
- Maximum single public file: {max_gb} GB (private uploads uncapped).
- Folders are capped per {bw_window}-minute bandwidth window
  ({folder_gb} GB), not by stored total.
- Upload rate limit: {rate} attempts per IP per {window_min} minutes.
- Fair use: heavy uploaders are transparently slowed down; logged-in
  sessions are exempt.
- Identical bytes are stored once: `file_id` is the SHA-256 of the
  content, so re-uploading the same file reuses the blob.

## Language
The browser pages are rendered in Traditional Chinese or English by the
browser itself: an inline script reads navigator.languages, stores the pick
in a `lang` cookie and reloads once when needed (Traditional Chinese for
zh-TW/Hant/HK/MO browsers, English for everything else). Add ?lang=zh-TW or
?lang=en to any page to force one. JSON, plain text and this document are
always English. For scripted clients there is no language logic at all.

AI agents should prefer the JSON API endpoints above and use the returned `url` or `download_url` directly.
"""


@router.get("/api/llms.txt", response_class=PlainTextResponse)
@router.get("/llms.txt", response_class=PlainTextResponse)
async def public_llms(request: Request):
    base = base_url(request)
    return LLMS_TEMPLATE.format(
        base=base,
        max_gb=settings.max_file_size // 1024**3,
        bw_window=settings.bw_window_seconds // 60,
        folder_gb=settings.bw_folder_hard_bytes // 1024**3,
        rate=settings.rate_limit_max_uploads,
        window_min=settings.rate_limit_window // 60,
    )
