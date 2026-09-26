"""API index + machine-readable docs (llms.txt)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from ..config import settings
from ..negotiation import wants_html
from ..ui import endpoint_card, page

router = APIRouter()


def _api_payload(request: Request) -> dict:
    base = str(request.base_url).rstrip("/")
    return {
        "name": "CaveMan Drop public API",
        "description": "Anonymous file sharing. Upload a file, get a permanent share link back. No auth required.",
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
                "notes": "Creates an empty public folder and returns share/upload URLs.",
            },
            "upload": {
                "method": "POST",
                "url": f"{base}/api/public/upload",
                "form_fields": {
                    "file": "the file to upload (required)",
                    "folder": "existing folder_id to add this file to (optional — omitted means a single direct file, no folder is created)",
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
            "upload_page": {
                "method": "GET",
                "url": f"{base}/upload",
                "notes": "Human-friendly anonymous upload page that returns a file URL and share URL.",
            },
            "ai_docs": {
                "method": "GET",
                "url": f"{base}/api/llms.txt",
            },
            "browse_page": {
                "method": "GET",
                "url": f"{base}/f/{{folder_id}}",
                "notes": "Human-friendly page for browsing/downloading/uploading to a folder — share this link with others.",
            },
        },
    }


@router.get("/api")
async def api_root(request: Request):
    if wants_html(request):
        return HTMLResponse(
            page(
                "API",
                """<mdui-card variant="filled" class="card-pad hero">
          <h1>API 索引</h1>
          <p>以下每個端點：程式與 AI 拿到 JSON（加 <code>?format=json</code> 可強制），瀏覽器則看到 MDUI 控制台。</p>
          <div class="form-row">
            <a href="/llms.txt"><mdui-button variant="outlined">給 AI 的 llms.txt</mdui-button></a>
            <a href="/docs/api"><mdui-button variant="text">完整參考</mdui-button></a>
          </div>
        </mdui-card>
        <div class="stack">
        """
                + endpoint_card("POST", "/api/public/upload", "匿名上傳 — multipart 欄位 'file'，選填 'folder'。", "/upload")
                + endpoint_card("POST", "/api/public/chunk → /api/public/merge_chunks", "分段上傳：先傳分塊再合併，大檔案自動使用。", "/upload")
                + endpoint_card("POST", "/api/public/folder", "建立空資料夾，回傳分享與上傳網址。", "/upload")
                + endpoint_card("GET", "/api/public/folder/{folder_id}", "資料夾資訊、檔案清單與下載網址。", None)
                + endpoint_card("GET", "/api/public/file/{folder_id}/{file_id}", "單一檔案資訊與下載網址。", None)
                + endpoint_card("GET", "/dl/pub/{folder_id}/{file_id}", "下載檔案本體。支援 Range 續傳 / 並行。", None)
                + endpoint_card("GET", "/api/files", "私人檔案清單（需密碼登入）。", "/login")
                + endpoint_card("POST", "/api/upload_chunk + /api/merge_chunks", "私人分段上傳（登入後不限速）。", "/login")
                + "</div>",
                active="api",
            )
        )
    return _api_payload(request)


LLMS_TEMPLATE = """# CaveMan Drop Public File API

This is an anonymous public file-sharing API. No authentication is required.
CORS is enabled for browser JavaScript and AI agents.

## Upload a file
POST {base}/api/public/upload
Content-Type: multipart/form-data
Fields:
- file: required file
- folder: optional existing folder_id (adds to that folder; omit for a
  single direct file — no folder is created)
Returns JSON containing `url` and `download_url` (plus `folder_url` etc.
only when a folder was used).

## Create an empty public folder
POST {base}/api/public/folder
Returns a folder_id plus `folder_url`, `upload_url`, and `folder_api_url`.

## Chunked upload (browsers + scripts)
POST {base}/api/public/chunk (multipart: `file_chunk`, `upload_id` (uuid),
`index` (0-based), `filename`) — send parts in parallel, then
POST {base}/api/public/merge_chunks (JSON: `upload_id`, `filename`,
`total_chunks`, optional `folder`) to assemble. Returns the same payload
as the single-POST upload. POST 1 MB to /api/public/probe first for a
speed-based thread recommendation (slow links get 32/64/128).

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

## Human upload/share page
GET {base}/upload
GET {base}/f/{{folder_id}}

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

AI agents should prefer the JSON API endpoints above and use the returned `url` or `download_url` directly.
"""


@router.get("/api/llms.txt", response_class=PlainTextResponse)
@router.get("/llms.txt", response_class=PlainTextResponse)
async def public_llms(request: Request):
    base = str(request.base_url).rstrip("/")
    return LLMS_TEMPLATE.format(
        base=base,
        max_gb=settings.max_file_size // 1024**3,
        bw_window=settings.bw_window_seconds // 60,
        folder_gb=settings.bw_folder_hard_bytes // 1024**3,
        rate=settings.rate_limit_max_uploads,
        window_min=settings.rate_limit_window // 60,
    )
