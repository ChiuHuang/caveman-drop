"""Anonymous public share API (no auth, CORS-open, rate-limited).

POST endpoints always return JSON (browser upload forms use fetch and parse
JSON). GET endpoints return JSON to agents/curl and an MDUI HTML console to
browsers. Downloads always stream bytes.
"""

from __future__ import annotations

import html
import json
import mimetypes
import os
import re
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from ..config import settings
from ..negotiation import wants_html
from ..storage import (
    check_rate_limit,
    folder_lock,
    public_folder_dir,
    public_folder_files,
    stream_download,
    validate_public_id,
)
from ..ui import file_rows, page

router = APIRouter()


@router.post("/api/public/upload")
async def public_upload(
    request: Request,
    file: UploadFile = File(...),
    folder: Optional[str] = Form(None),
):
    """Anonymous upload. Omit folder to create a new share folder."""
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(ip)

    if folder:
        folder_id = folder
        validate_public_id(folder_id, "folder id")
        fdir = public_folder_dir(folder_id)
        if not os.path.isdir(fdir):
            raise HTTPException(404, "Folder not found")
    else:
        import uuid

        folder_id = str(uuid.uuid4())
        fdir = public_folder_dir(folder_id)
        os.makedirs(fdir, exist_ok=True)

    # Serialize uploads into the same folder so the aggregate quota cannot be
    # bypassed by two concurrent requests racing on the file count/size.
    async with folder_lock(folder_id):
        existing_files = public_folder_files(folder_id)
        becomes_multi = len(existing_files) >= 1
        existing_total = sum(f["size"] for f in existing_files)
        known_size = getattr(file, "size", None)

        if known_size is not None:
            if known_size > settings.max_file_size:
                raise HTTPException(
                    413,
                    f"File exceeds the {settings.max_file_size // 1024**3}GB per-file limit",
                )
            if becomes_multi and existing_total + known_size > settings.max_multi_folder_total:
                raise HTTPException(
                    413,
                    f"This folder can hold at most {settings.max_multi_folder_total // 1024**3}GB "
                    "once it contains more than one file",
                )

        import uuid

        fid = str(uuid.uuid4())
        original_name = os.path.basename(file.filename or "unnamed") or "unnamed"
        _, ext = os.path.splitext(original_name)
        ext = ext[:32] if re.fullmatch(r"\.[A-Za-z0-9._-]+", ext or "") else ""
        dest = os.path.join(fdir, fid + ext)
        written = 0
        CHUNK = 1024 * 1024

        try:
            with open(dest, "wb") as out:
                while True:
                    chunk = await file.read(CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > settings.max_file_size:
                        raise HTTPException(
                            413,
                            f"File exceeds the {settings.max_file_size // 1024**3}GB per-file limit",
                        )
                    if becomes_multi and existing_total + written > settings.max_multi_folder_total:
                        raise HTTPException(
                            413,
                            f"This folder can hold at most {settings.max_multi_folder_total // 1024**3}GB "
                            "once it contains more than one file",
                        )
                    out.write(chunk)
        except HTTPException:
            if os.path.exists(dest):
                os.remove(dest)
            raise
        finally:
            await file.close()

        content_type = (
            file.content_type
            or mimetypes.guess_type(original_name)[0]
            or "application/octet-stream"
        )
        with open(os.path.join(fdir, fid + ".json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "filename": original_name,
                    "ext": ext,
                    "content_type": content_type,
                    "ctime": __import__("time").time(),
                },
                f,
            )

    base = str(request.base_url).rstrip("/")
    download_url = f"{base}/dl/pub/{folder_id}/{fid}"
    folder_url = f"{base}/f/{folder_id}"
    return {
        "success": True,
        "folder_id": folder_id,
        "file_id": fid,
        "filename": original_name,
        "size_bytes": written,
        "content_type": content_type,
        "url": download_url,
        "download_url": download_url,
        "folder_url": folder_url,
        "share_url": folder_url,
        "folder_api_url": f"{base}/api/public/folder/{folder_id}",
        "file_api_url": f"{base}/api/public/file/{folder_id}/{fid}",
    }


@router.post("/api/public/folder")
async def public_create_folder(request: Request):
    """Create an empty public folder and return share/upload/API URLs."""
    import uuid

    folder_id = str(uuid.uuid4())
    os.makedirs(public_folder_dir(folder_id), exist_ok=True)
    base = str(request.base_url).rstrip("/")
    return {
        "success": True,
        "folder_id": folder_id,
        "folder_url": f"{base}/f/{folder_id}",
        "upload_url": f"{base}/f/{folder_id}",
        "folder_api_url": f"{base}/api/public/folder/{folder_id}",
    }


@router.get("/api/public/file/{folder_id}/{file_id}")
async def public_file_api(request: Request, folder_id: str, file_id: str):
    """Metadata + direct URL for one public file (HTML console for browsers)."""
    fdir = public_folder_dir(folder_id)
    jp = os.path.join(fdir, file_id + ".json")
    if not os.path.exists(jp):
        raise HTTPException(404, "File not found")
    try:
        with open(jp, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        raise HTTPException(404, "File metadata is invalid")
    path = os.path.join(fdir, file_id + meta.get("ext", ""))
    if not os.path.exists(path):
        raise HTTPException(404, "File not found")
    base = str(request.base_url).rstrip("/")
    payload = {
        "folder_id": folder_id,
        "file_id": file_id,
        "filename": meta.get("filename", file_id),
        "size_bytes": os.path.getsize(path),
        "content_type": meta.get("content_type", "application/octet-stream"),
        "download_url": f"{base}/dl/pub/{folder_id}/{file_id}",
        "url": f"{base}/dl/pub/{folder_id}/{file_id}",
    }
    if not wants_html(request):
        return payload
    return HTMLResponse(
        page(
            payload["filename"],
            f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(payload["filename"])}</h1>
          <p>{payload["size_bytes"]} 位元組 · {html.escape(payload["content_type"])}</p>
          <div class="form-row">
            <a href="{payload["download_url"]}"><mdui-button icon="download">下載</mdui-button></a>
            <mdui-button variant="outlined" data-preview="{payload["download_url"]}?preview=1" data-name="{html.escape(payload["filename"])}">預覽</mdui-button>
            <mdui-button variant="outlined" data-copy="{payload["download_url"]}">複製連結</mdui-button>
            <a href="{base}/f/{folder_id}"><mdui-button variant="text">開啟資料夾</mdui-button></a>
          </div>
        </mdui-card>
        <mdui-card variant="outlined" class="card-pad">
          <h2>API</h2>
          <pre class="curl">GET {base}/api/public/file/{folder_id}/{file_id}</pre>
        </mdui-card>""",
            active="upload",
        )
    )


@router.get("/api/public/folder/{folder_id}")
async def public_folder_api(request: Request, folder_id: str):
    """Folder metadata + files (folder UI for browsers)."""
    fdir = public_folder_dir(folder_id)
    if not os.path.isdir(fdir):
        raise HTTPException(404, "Folder not found")
    base = str(request.base_url).rstrip("/")
    files = public_folder_files(folder_id)
    for f in files:
        f["download_url"] = f"{base}/dl/pub/{folder_id}/{f['id']}"
        f["url"] = f["download_url"]
        f["file_api_url"] = f"{base}/api/public/file/{folder_id}/{f['id']}"
    if not wants_html(request):
        return {
            "folder_id": folder_id,
            "folder_url": f"{base}/f/{folder_id}",
            "share_url": f"{base}/f/{folder_id}",
            "upload_url": f"{base}/f/{folder_id}",
            "files": files,
        }
    return HTMLResponse(
        page(
            f"資料夾 {folder_id[:8]}（API）",
            f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>資料夾 API 控制台</h1>
          <p><code>{html.escape(folder_id)}</code></p>
          <div class="form-row">
            <a href="{base}/f/{folder_id}"><mdui-button>開啟資料夾介面</mdui-button></a>
            <mdui-button variant="outlined" data-copy="{base}/api/public/folder/{html.escape(folder_id)}">複製 API 網址</mdui-button>
          </div>
        </mdui-card>
        <mdui-card variant="outlined" class="card-pad">
          <h2>檔案（{len(files)}）</h2>
          {file_rows(files, folder_id, base)}
        </mdui-card>""",
            active="api",
        )
    )


@router.get("/dl/pub/{folder_id}/{file_id}")
async def public_download(request: Request, folder_id: str, file_id: str, preview: bool = False):
    validate_public_id(file_id, "file id")
    fdir = public_folder_dir(folder_id)
    jp = os.path.join(fdir, file_id + ".json")
    if not os.path.exists(jp):
        raise HTTPException(404)
    with open(jp, encoding="utf-8") as f:
        meta = json.load(f)
    path = os.path.join(fdir, file_id + meta.get("ext", ""))
    ctype = meta.get("content_type") if preview else None
    return stream_download(request, path, meta["filename"], inline=preview, content_type=ctype)
