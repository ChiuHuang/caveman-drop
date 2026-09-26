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
            "max_file_size_human": f"{settings.max_file_size // 1024**3} GB",
            "max_multi_file_folder_total_bytes": settings.max_multi_folder_total,
            "max_multi_file_folder_total_human": (
                f"{settings.max_multi_folder_total // 1024**3} GB combined, "
                "once a folder holds more than one file"
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
                    "folder": "existing folder_id to add this file to (optional — omit to start a new folder)",
                },
                "example_curl": f'curl -F "file=@myfile.txt" {base}/api/public/upload',
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
          <h1>API index</h1>
          <p>Every endpoint below returns JSON to scripts and agents
          (<code>?format=json</code> forces it) and renders an MDUI console for browsers.</p>
          <div class="form-row">
            <a href="/llms.txt"><mdui-button variant="outlined">llms.txt for agents</mdui-button></a>
            <a href="/docs/api"><mdui-button variant="text">Full reference</mdui-button></a>
          </div>
        </mdui-card>
        <div class="stack">
        """
                + endpoint_card("POST", "/api/public/upload", "Anonymous upload — multipart field 'file', optional 'folder'.", "/upload")
                + endpoint_card("POST", "/api/public/folder", "Create an empty folder; returns share/upload URLs.", "/upload")
                + endpoint_card("GET", "/api/public/folder/{folder_id}", "Folder metadata, files, download URLs.", None)
                + endpoint_card("GET", "/api/public/file/{folder_id}/{file_id}", "One file's metadata and URL.", None)
                + endpoint_card("GET", "/dl/pub/{folder_id}/{file_id}", "Download bytes. Range requests supported.", None)
                + endpoint_card("GET", "/api/files", "Private file list (password session required).", "/login")
                + endpoint_card("POST", "/api/upload_chunk + /api/merge_chunks", "Private chunked/resumable upload.", "/login")
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
- folder: optional existing folder_id
Returns JSON containing `url`, `download_url`, `folder_url`, `folder_api_url`, and `file_api_url`.

## Create an empty public folder
POST {base}/api/public/folder
Returns a folder_id plus `folder_url`, `upload_url`, and `folder_api_url`.

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
- Maximum single file: {max_gb} GB.
- If a folder contains more than one file, combined folder size is limited to {folder_gb} GB.
- Upload rate limit: {rate} attempts per IP per {window_min} minutes.

AI agents should prefer the JSON API endpoints above and use the returned `url` or `download_url` directly.
"""


@router.get("/api/llms.txt", response_class=PlainTextResponse)
@router.get("/llms.txt", response_class=PlainTextResponse)
async def public_llms(request: Request):
    base = str(request.base_url).rstrip("/")
    return LLMS_TEMPLATE.format(
        base=base,
        max_gb=settings.max_file_size // 1024**3,
        folder_gb=settings.max_multi_folder_total // 1024**3,
        rate=settings.rate_limit_max_uploads,
        window_min=settings.rate_limit_window // 60,
    )
