"""Anonymous public share API (no auth, CORS-open, rate-limited).

POST endpoints always return JSON (browser upload forms use fetch and parse
JSON). GET endpoints return JSON to agents/curl and an MDUI HTML console to
browsers. Downloads always stream bytes. File ids are the sha256 of the content
(see app/storage.py), so identical files share one stored copy.
"""

from __future__ import annotations

import html
import mimetypes
import os
import re
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..config import settings
from ..negotiation import wants_html
from ..storage import (
    MAX_CHUNK_BYTES,
    assemble_chunks,
    bin_path,
    bw_pace,
    bw_record,
    bw_status,
    check_rate_limit,
    chunk_dir,
    clean_name,
    client_ip,
    create_public_folder,
    entry_meta,
    folder_lock,
    payload_path,
    probe_check,
    public_folder_dir,
    public_folder_files,
    public_folder_name,
    resolve_public_folder,
    save_entry,
    single_blob,
    single_meta,
    speed_probe,
    store_blob,
    stream_download,
    tag_ip,
    tagged_threads,
    validate_file_id,
    validate_public_id,
    validate_upload_id,
)
from ..ui import file_rows, fmt_size, page
from ..urls import base_url

router = APIRouter()


class PublicMergePayload(BaseModel):
    upload_id: str
    filename: str
    total_chunks: int
    folder: Optional[str] = None


async def _receive_to_bin(
    file: UploadFile, ip: str, folder_id: str | None
) -> tuple[str, int, bool]:
    """Stream an upload into a temp file, then file it in the bin store by sha256.

    Returns (file_id, bytes, already_stored). Identical bytes always get the same
    id and reuse the stored blob, so re-uploading a file never writes a second copy.
    """
    import hashlib
    import uuid

    dest = os.path.join(settings.tmp_dir, f"up_{uuid.uuid4()}")
    digest = hashlib.sha256()
    written = 0
    CHUNK = 1024 * 1024
    try:
        with open(dest, "wb") as out:
            paced_at = 0
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
                digest.update(chunk)
                out.write(chunk)
                bw_record(ip, folder_id, len(chunk))
                if written - paced_at >= CHUNK:
                    await bw_pace(ip, written - paced_at, bw_status(ip, folder_id)["throttle_mbps"])
                    paced_at = written
        file_id = digest.hexdigest()
        deduped = os.path.exists(bin_path(file_id))
        store_blob(dest, file_id)
        return file_id, written, deduped
    except HTTPException:
        if os.path.exists(dest):
            os.remove(dest)
        raise
    finally:
        await file.close()


def _file_meta(original_name: str, size: int) -> dict:
    _, ext = os.path.splitext(original_name)
    ext = ext[:32] if re.fullmatch(r"\.[A-Za-z0-9._-]+", ext or "") else ""
    return {
        "filename": original_name,
        "ext": ext,
        "content_type": mimetypes.guess_type(original_name)[0] or "application/octet-stream",
        "size": size,
    }


@router.post("/api/public/upload")
async def public_upload(
    request: Request,
    file: UploadFile = File(...),
    folder: Optional[str] = Form(None),
):
    """Anonymous upload. No folder = single direct file, no folder created.

    `file_id` is the sha256 of the content, so the same file always gets the same
    id and link. `folder` accepts an existing folder id or a free-text name
    (which creates a new folder named after it).
    """
    ip = client_ip(request)
    check_rate_limit(ip)

    if folder:
        return await _upload_to_folder(request, ip, file, resolve_public_folder(folder))

    original_name = os.path.basename(file.filename or "unnamed") or "unnamed"
    meta = _file_meta(original_name, 0)
    fid, written, deduped = await _receive_to_bin(file, ip, None)
    meta["size"] = written
    meta["content_type"] = file.content_type or meta["content_type"]
    save_entry(settings.single_dir, fid, meta)

    base = base_url(request)
    download_url = f"{base}/dl/s/{fid}"
    return {
        "success": True,
        "file_id": fid,
        "filename": original_name,
        "size_bytes": written,
        "content_type": meta["content_type"],
        "deduplicated": deduped,
        "url": download_url,
        "download_url": download_url,
        "file_api_url": f"{base}/api/public/single/{fid}",
    }


async def _upload_to_folder(request: Request, ip: str, file: UploadFile, folder: str):
    folder_id = folder
    validate_public_id(folder_id, "folder id")
    fdir = public_folder_dir(folder_id)
    if not os.path.isdir(fdir):
        raise HTTPException(404, "Folder not found")

    async with folder_lock(folder_id):
        known_size = getattr(file, "size", None)

        if known_size is not None and known_size > settings.max_file_size:
            raise HTTPException(
                413,
                f"File exceeds the {settings.max_file_size // 1024**3}GB per-file limit",
            )

        original_name = os.path.basename(file.filename or "unnamed") or "unnamed"
        meta = _file_meta(original_name, 0)
        fid, written, deduped = await _receive_to_bin(file, ip, folder_id)
        meta["size"] = written
        meta["content_type"] = file.content_type or meta["content_type"]
        save_entry(fdir, fid, meta)

    base = base_url(request)
    download_url = f"{base}/dl/pub/{folder_id}/{fid}"
    folder_url = f"{base}/f/{folder_id}"
    return {
        "success": True,
        "folder_id": folder_id,
        "folder_name": public_folder_name(folder_id),
        "file_id": fid,
        "filename": original_name,
        "size_bytes": written,
        "content_type": meta["content_type"],
        "deduplicated": deduped,
        "url": download_url,
        "download_url": download_url,
        "folder_url": folder_url,
        "share_url": folder_url,
        "folder_api_url": f"{base}/api/public/folder/{folder_id}",
        "file_api_url": f"{base}/api/public/file/{folder_id}/{fid}",
    }


@router.post("/api/public/folder")
async def public_create_folder(request: Request):
    """Create an empty public folder under a free-text name and return its URLs."""
    name = ""
    try:
        body = await request.json()
        if isinstance(body, dict):
            name = clean_name(str(body.get("name", "") or ""))
    except Exception:
        pass
    folder_id, meta = create_public_folder(name)
    base = base_url(request)
    return {
        "success": True,
        "folder_id": folder_id,
        "folder_name": meta["name"],
        "folder_url": f"{base}/f/{folder_id}",
        "upload_url": f"{base}/f/{folder_id}",
        "folder_api_url": f"{base}/api/public/folder/{folder_id}",
    }


@router.post("/api/public/chunk")
async def public_chunk(
    request: Request,
    file_chunk: UploadFile = File(...),
    upload_id: str = Form(...),
    index: int = Form(...),
    filename: str = Form(...),
):
    """One chunk of a public chunked upload. Returns the bandwidth verdict."""
    ip = client_ip(request)
    validate_upload_id(upload_id)
    if index < 0 or index >= settings.max_chunked_parts:
        raise HTTPException(400, "Chunk index out of range")
    data = await file_chunk.read()
    await file_chunk.close()
    if len(data) > MAX_CHUNK_BYTES:
        raise HTTPException(413, "Chunk too large")
    cdir = chunk_dir("pub", upload_id)
    with open(os.path.join(cdir, f"part_{index}"), "wb") as f:
        f.write(data)
    bw_record(ip, None, len(data))
    status = bw_status(ip)
    await bw_pace(ip, len(data), status["throttle_mbps"])
    status["threads_tagged"] = tagged_threads(ip)
    return {"ok": True, **status}


@router.post("/api/public/merge_chunks")
async def public_merge_chunks(request: Request, payload: PublicMergePayload):
    """Assemble a public chunked upload. No folder = single direct file.

    `folder` is an existing folder id or a free-text name for a new folder.
    """
    ip = client_ip(request)
    check_rate_limit(ip)
    validate_upload_id(payload.upload_id)

    original_name = os.path.basename(payload.filename or "unnamed") or "unnamed"
    _, ext = os.path.splitext(original_name)
    ext = ext[:32] if re.fullmatch(r"\.[A-Za-z0-9._-]+", ext or "") else ""
    cdir = os.path.join(settings.tmp_dir, f"pub_{payload.upload_id}")
    content_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    base = base_url(request)
    entry = {"filename": original_name, "ext": ext, "content_type": content_type}

    if payload.folder:
        folder_id = resolve_public_folder(payload.folder)
        validate_public_id(folder_id, "folder id")
        fdir = public_folder_dir(folder_id)
        if not os.path.isdir(fdir):
            raise HTTPException(404, "Folder not found")
        async with folder_lock(folder_id):
            fid, written = assemble_chunks(cdir, payload.total_chunks, settings.max_file_size)
            save_entry(fdir, fid, {**entry, "size": written})
            bw_record(ip, folder_id, written)
        download_url = f"{base}/dl/pub/{folder_id}/{fid}"
        folder_url = f"{base}/f/{folder_id}"
        return {
            "success": True,
            "folder_id": folder_id,
            "folder_name": public_folder_name(folder_id),
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

    fid, written = assemble_chunks(cdir, payload.total_chunks, settings.max_file_size)
    save_entry(settings.single_dir, fid, {**entry, "size": written})
    bw_record(ip, None, written)
    download_url = f"{base}/dl/s/{fid}"
    return {
        "success": True,
        "file_id": fid,
        "filename": original_name,
        "size_bytes": written,
        "content_type": content_type,
        "url": download_url,
        "download_url": download_url,
        "file_api_url": f"{base}/api/public/single/{fid}",
    }


@router.get("/api/public/single/{file_id}")
async def public_single_api(request: Request, file_id: str):
    """Metadata + direct URL for one single (folderless) public file."""
    try:
        meta = single_meta(file_id)
    except HTTPException:
        raise HTTPException(404, "File not found")
    base = base_url(request)
    payload = {
        "file_id": file_id,
        "filename": meta.get("filename", file_id),
        "size_bytes": meta["size"],
        "content_type": meta.get("content_type", "application/octet-stream"),
        "download_url": f"{base}/dl/s/{file_id}",
        "url": f"{base}/dl/s/{file_id}",
    }
    if not wants_html(request):
        return payload
    return HTMLResponse(
        page(
            payload["filename"],
            f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(payload["filename"])}</h1>
          <p>{fmt_size(payload["size_bytes"])} · {html.escape(payload["content_type"])}</p>
          <div class="form-row">
            <a href="{payload["download_url"]}"><mdui-button icon="download">下載</mdui-button></a>
            <mdui-button variant="outlined" data-preview="{payload["download_url"]}?preview=1" data-name="{html.escape(payload["filename"])}">預覽</mdui-button>
            <mdui-button variant="outlined" data-copy="{payload["download_url"]}">複製連結</mdui-button>
          </div>
        </mdui-card>""",
            active="upload",
        )
    )


@router.get("/dl/s/{file_id}")
async def public_single_download(request: Request, file_id: str, preview: bool = False):
    try:
        meta = single_meta(file_id)
    except HTTPException:
        raise HTTPException(404)
    path = single_blob(file_id, meta.get("ext", ""))
    ctype = meta.get("content_type") if preview else None
    return stream_download(request, path, meta.get("filename", file_id), inline=preview, content_type=ctype)


@router.post("/api/public/probe")
async def public_probe(request: Request, probe: UploadFile = File(...), ms: Optional[str] = Form(None)):
    """Speed probe: returns the thread count this IP should use."""
    ip = client_ip(request)
    probe_check(ip)
    data = await probe.read()
    await probe.close()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Probe too large")
    threads, bps = speed_probe(len(data), request, ms)
    tag_ip(ip, threads)
    return {"threads": threads, "mbps": round(bps * 8 / 1_000_000, 2), "you": ip}


@router.get("/api/public/file/{folder_id}/{file_id}")
async def public_file_api(request: Request, folder_id: str, file_id: str):
    """Metadata + direct URL for one public file (HTML console for browsers)."""
    fdir = public_folder_dir(folder_id)
    meta = entry_meta(fdir, file_id)
    if meta is None:
        raise HTTPException(404, "File not found")
    base = base_url(request)
    payload = {
        "folder_id": folder_id,
        "file_id": file_id,
        "filename": meta.get("filename", file_id),
        "size_bytes": meta["size"],
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
    base = base_url(request)
    files = public_folder_files(folder_id)
    for f in files:
        f["download_url"] = f"{base}/dl/pub/{folder_id}/{f['id']}"
        f["url"] = f["download_url"]
        f["file_api_url"] = f"{base}/api/public/file/{folder_id}/{f['id']}"
    if not wants_html(request):
        return {
            "folder_id": folder_id,
            "folder_name": public_folder_name(folder_id),
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
    validate_file_id(file_id)
    fdir = public_folder_dir(folder_id)
    meta = entry_meta(fdir, file_id)
    if meta is None:
        raise HTTPException(404)
    path = payload_path(file_id, fdir, meta.get("ext", ""))
    ctype = meta.get("content_type") if preview else None
    return stream_download(request, path, meta["filename"], inline=preview, content_type=ctype)
