"""Anonymous public share API (no auth, CORS-open, rate-limited).

POST endpoints always return JSON (browser upload forms use fetch and parse
JSON). GET endpoints return JSON to agents/curl and an MDUI HTML console to
browsers. Downloads always stream bytes. File ids are the sha256 of the content
(see app/storage.py), so identical files share one stored copy.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import mimetypes
import os
import re
from typing import Optional
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from ..config import settings
from ..negotiation import wants_html
from ..storage import (
    MAX_CHUNK_BYTES,
    PERMS,
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
    public_folder_meta,
    public_folder_name,
    public_file_by_id,
    resolve_public_folder,
    resolve_short_code,
    save_entry,
    set_public_folder_perm,
    short_code,
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
    zip_stream_request,
)
from ..i18n import lang_for, t
from ..ui import file_rows, fmt_size, page
from ..auth import session_sid
from ..urls import base_url

router = APIRouter()


class PublicMergePayload(BaseModel):
    upload_id: str
    filename: str
    total_chunks: int
    folder: Optional[str] = None
    description: str = ""


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


def _file_meta(original_name: str, size: int, description: str = "") -> dict:
    _, ext = os.path.splitext(original_name)
    ext = ext[:32] if re.fullmatch(r"\.[A-Za-z0-9._-]+", ext or "") else ""
    return {
        "filename": original_name,
        "ext": ext,
        "content_type": mimetypes.guess_type(original_name)[0] or "application/octet-stream",
        "size": size,
        "description": clean_name(description, 200),
    }


def _short_url(base: str, file_id: str, ext: str) -> str:
    """catbox-style share link: /<short code>.<ext> (CDN-cacheable).

    When USERCONTENT_HOST is set (the default deployment), the link points at
    that CDN host instead of the serving host, so the copy button hands out the
    shortest, cacheable URL by default. /usercontent/<code>.<ext> stays as an
    alias for links handed out earlier."""
    code = short_code(file_id)
    if not code:
        return ""
    if settings.usercontent_host:
        return f"https://{settings.usercontent_host}/{code}{ext}"
    return f"{base}/{code}{ext}"


def _probably_browser(request: Request) -> bool:
    """Does this request look like a browser that will keep cookies?

    Ownership only makes sense for sessions: a browser POST (fetch or form)
    always sends Origin, and browsers send a Mozilla-ish User-Agent. curl, the
    AI tools and scripts get folders without an owner —they would not keep a
    session cookie anyway.
    """
    ua = request.headers.get("user-agent", "")
    return "Mozilla" in ua or bool(request.headers.get("origin"))


def _folder_owner(request: Request) -> str:
    """The sid this browser session already carries, minting one for browser
    requests. Cookie-less scripts get "" —their folders stay ownerless."""
    if request.session.get("sid"):
        return request.session["sid"]
    return session_sid(request) if _probably_browser(request) else ""


def _folder_gate(request: Request, folder_id: str) -> dict:
    """Access flags for a public folder, from folder.json + this request.

    perm: readonly (list + download), upload (dropbox), or both (default, what
    folders without a perm always had). The creating session (`owner` sid) and
    a signed-in admin bypass the perm entirely and may manage the folder.

    404s when the folder does not exist.
    """
    meta = public_folder_meta(folder_id)
    if not meta or not os.path.isdir(public_folder_dir(folder_id)):
        raise HTTPException(404, "Folder not found")
    perm = meta.get("perm") if meta.get("perm") in PERMS else "both"
    owner = str(meta.get("owner", "") or "")
    is_owner = (bool(owner) and owner == (request.session.get("sid") or "")) \
        or bool(request.session.get("auth"))
    return {
        **meta,
        "perm": perm,
        "owner": owner,
        "can_read": is_owner or perm in ("readonly", "both"),
        "can_upload": is_owner or perm in ("upload", "both"),
        "can_manage": is_owner,
        "owned": bool(owner) and owner == (request.session.get("sid") or ""),
    }


@router.post("/api/public/upload")
async def public_upload(
    request: Request,
    file: UploadFile = File(...),
    folder: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
):
    """Anonymous upload. No folder = single direct file, no folder created.

    `file_id` is the sha256 of the content, so the same file always gets the same
    id and link. `folder` accepts an existing folder id or a free-text name
    (which creates a new folder named after it). `description` is optional free
    text shown next to the file.
    """
    ip = client_ip(request)
    check_rate_limit(ip)

    if folder:
        return await _upload_to_folder(
            request,
            ip,
            file,
            resolve_public_folder(
                folder,
                t(lang_for(request), "unnamed_folder"),
                owner=_folder_owner(request),
            ),
            description,
        )

    original_name = os.path.basename(file.filename or "unnamed") or "unnamed"
    meta = _file_meta(original_name, 0, description or "")
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
        "description": meta["description"],
        "size_bytes": written,
        "content_type": meta["content_type"],
        "deduplicated": deduped,
        "short_url": _short_url(base, fid, meta["ext"]),
        "url": download_url,
        "download_url": download_url,
        "file_api_url": f"{base}/api/public/single/{fid}",
    }


async def _upload_to_folder(
    request: Request, ip: str, file: UploadFile, folder: str, description: str = ""
):
    folder_id = folder
    validate_public_id(folder_id, "folder id")
    gate = _folder_gate(request, folder_id)
    if not gate["can_upload"]:
        raise HTTPException(403, "This folder is read-only")
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
        meta = _file_meta(original_name, 0, description or "")
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
        "folder_perm": gate["perm"],
        "file_id": fid,
        "filename": original_name,
        "description": meta["description"],
        "size_bytes": written,
        "content_type": meta["content_type"],
        "deduplicated": deduped,
        "short_url": _short_url(base, fid, meta["ext"]),
        "url": download_url,
        "download_url": download_url,
        "folder_url": folder_url,
        "share_url": folder_url,
        "folder_api_url": f"{base}/api/public/folder/{folder_id}",
        "file_api_url": f"{base}/api/public/file/{folder_id}/{fid}",
    }


@router.post("/api/public/folder")
async def public_create_folder(request: Request):
    """Create an empty public folder and return its URLs.

    Body (JSON): `name` (free text), `perm` = readonly / upload / both —what
    non-owners may do. The folder is assigned to the calling browser session
    (a stable sid cookie), so its creator can rename, delete and re-permission
    it without logging in; folders created by curl scripts get no owner.
    """
    name = ""
    perm = "both"
    try:
        body = await request.json()
        if isinstance(body, dict):
            name = clean_name(str(body.get("name", "") or ""))
            perm = str(body.get("perm", "") or "") or "both"
    except Exception:
        pass
    if perm not in PERMS:
        perm = "both"
    # A browser session owns the folder; a script that sends no cookies does not.
    owner = _folder_owner(request)
    folder_id, meta = create_public_folder(
        name, t(lang_for(request), "unnamed_folder"), perm=perm, owner=owner
    )
    base = base_url(request)
    return {
        "success": True,
        "folder_id": folder_id,
        "folder_name": meta["name"],
        "perm": meta["perm"],
        "owned": bool(owner),
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
    `description` is optional free text stored with the file.
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
    description = clean_name(payload.description, 200)
    entry = {
        "filename": original_name,
        "ext": ext,
        "content_type": content_type,
        "description": description,
    }

    if payload.folder:
        folder_id = resolve_public_folder(
            payload.folder,
            t(lang_for(request), "unnamed_folder"),
            owner=_folder_owner(request),
        )
        validate_public_id(folder_id, "folder id")
        if not _folder_gate(request, folder_id)["can_upload"]:
            raise HTTPException(403, "This folder is read-only")
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
            "description": description,
            "size_bytes": written,
            "content_type": content_type,
            "short_url": _short_url(base, fid, ext),
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
        "description": description,
        "size_bytes": written,
        "content_type": content_type,
        "short_url": _short_url(base, fid, ext),
        "url": download_url,
        "download_url": download_url,
        "file_api_url": f"{base}/api/public/single/{fid}",
    }


@router.get("/usercontent/{code}")
async def usercontent(request: Request, code: str, preview: bool = False):
    """Short catbox-style download path: /usercontent/<6-or-more chars>.<ext>.

    The code is the shortest unique prefix of the file's sha256, so the URL is
    stable forever and safe to cache at a CDN (immutable Cache-Control).
    Public files only —private entries never resolve here.
    """
    stem = code.rsplit(".", 1)[0] if "." in code else code
    file_id = resolve_short_code(stem)
    if not file_id:
        raise HTTPException(404, "Not found")
    found = public_file_by_id(file_id)
    if found is None:
        raise HTTPException(404, "Not found")
    dirname, meta = found
    path = payload_path(file_id, dirname, meta.get("ext", ""))
    ctype = meta.get("content_type") if preview else None
    return stream_download(
        request,
        path,
        meta.get("filename", file_id),
        inline=preview,
        content_type=ctype,
        cache=True,
    )


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
        "description": meta.get("description", ""),
        "size_bytes": meta["size"],
        "content_type": meta.get("content_type", "application/octet-stream"),
        "short_url": _short_url(base, file_id, meta.get("ext", "")),
        "download_url": f"{base}/dl/s/{file_id}",
        "url": f"{base}/dl/s/{file_id}",
    }
    if not wants_html(request):
        return payload
    lang = lang_for(request)
    return HTMLResponse(
        page(
            payload["filename"],
            f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(payload["filename"])}</h1>
          <p>{fmt_size(payload["size_bytes"])} · {html.escape(payload["content_type"])}</p>
          <div class="form-row">
            <a href="{payload["download_url"]}"><mdui-button icon="download">{html.escape(t(lang, "btn_download"))}</mdui-button></a>
            <mdui-button variant="outlined" data-preview="{payload["download_url"]}?preview=1" data-name="{html.escape(payload["filename"])}">{html.escape(t(lang, "btn_preview"))}</mdui-button>
            <mdui-button variant="outlined" data-copy="{payload["download_url"]}">{html.escape(t(lang, "btn_copy_link"))}</mdui-button>
          </div>
        </mdui-card>""",
            active="upload",
            lang=lang,
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
    if not _folder_gate(request, folder_id)["can_read"]:
        raise HTTPException(403, "This folder is upload-only")
    fdir = public_folder_dir(folder_id)
    meta = entry_meta(fdir, file_id)
    if meta is None:
        raise HTTPException(404, "File not found")
    base = base_url(request)
    payload = {
        "folder_id": folder_id,
        "file_id": file_id,
        "filename": meta.get("filename", file_id),
        "description": meta.get("description", ""),
        "size_bytes": meta["size"],
        "content_type": meta.get("content_type", "application/octet-stream"),
        "short_url": _short_url(base, file_id, meta.get("ext", "")),
        "download_url": f"{base}/dl/pub/{folder_id}/{file_id}",
        "url": f"{base}/dl/pub/{folder_id}/{file_id}",
    }
    if not wants_html(request):
        return payload
    lang = lang_for(request)
    return HTMLResponse(
        page(
            payload["filename"],
            f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(payload["filename"])}</h1>
          <p>{fmt_size(payload["size_bytes"])} · {html.escape(payload["content_type"])}</p>
          <div class="form-row">
            <a href="{payload["download_url"]}"><mdui-button icon="download">{html.escape(t(lang, "btn_download"))}</mdui-button></a>
            <mdui-button variant="outlined" data-preview="{payload["download_url"]}?preview=1" data-name="{html.escape(payload["filename"])}">{html.escape(t(lang, "btn_preview"))}</mdui-button>
            <mdui-button variant="outlined" data-copy="{payload["download_url"]}">{html.escape(t(lang, "btn_copy_link"))}</mdui-button>
            <a href="{base}/f/{folder_id}"><mdui-button variant="text">{html.escape(t(lang, "open_folder"))}</mdui-button></a>
          </div>
        </mdui-card>
        <mdui-card variant="outlined" class="card-pad">
          <h2>API</h2>
          <pre class="curl">GET {base}/api/public/file/{folder_id}/{file_id}</pre>
        </mdui-card>""",
            active="upload",
            lang=lang,
        )
    )


@router.get("/api/public/folder/{folder_id}")
async def public_folder_api(request: Request, folder_id: str):
    """Folder metadata + files (folder UI for browsers). Read-perm respected:
    a read-only folder lists to anyone; an upload-only folder only lists for
    its owner (403 for everyone else)."""
    gate = _folder_gate(request, folder_id)
    if not gate["can_read"]:
        raise HTTPException(403, "This folder is upload-only")
    base = base_url(request)
    files = public_folder_files(folder_id)
    for f in files:
        f["download_url"] = f"{base}/dl/pub/{folder_id}/{f['id']}"
        f["url"] = f["download_url"]
        f["short_url"] = _short_url(base, f["id"], f.get("ext", ""))
        f["file_api_url"] = f"{base}/api/public/file/{folder_id}/{f['id']}"
    if not wants_html(request):
        return {
            "folder_id": folder_id,
            "folder_name": public_folder_name(folder_id),
            "folder_url": f"{base}/f/{folder_id}",
            "share_url": f"{base}/f/{folder_id}",
            "upload_url": f"{base}/f/{folder_id}",
            "perm": gate["perm"],
            "owned": gate["owned"],
            "can_upload": gate["can_upload"],
            "files": files,
        }
    lang = lang_for(request)
    return HTMLResponse(
        page(
            f"Folder {folder_id[:8]} (API)",
            f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(t(lang, "api_console_h"))}</h1>
          <p><code>{html.escape(folder_id)}</code></p>
          <div class="form-row">
            <a href="{base}/f/{folder_id}"><mdui-button>{html.escape(t(lang, "api_console_open"))}</mdui-button></a>
            <mdui-button variant="outlined" data-copy="{base}/api/public/folder/{html.escape(folder_id)}">{html.escape(t(lang, "copy_api_url"))}</mdui-button>
          </div>
        </mdui-card>
        <mdui-card variant="outlined" class="card-pad">
          <h2>{html.escape(t(lang, "files_h", n=len(files)))}</h2>
          {file_rows(lang, files, folder_id, base)}
        </mdui-card>""",
            active="api",
            lang=lang,
        )
    )


@router.get("/dl/pub/{folder_id}/{file_id}")
async def public_download(request: Request, folder_id: str, file_id: str, preview: bool = False):
    gate = _folder_gate(request, folder_id)
    if not gate["can_read"]:
        raise HTTPException(403, "This folder is upload-only")
    validate_file_id(file_id)
    fdir = public_folder_dir(folder_id)
    meta = entry_meta(fdir, file_id)
    if meta is None:
        raise HTTPException(404)
    path = payload_path(file_id, fdir, meta.get("ext", ""))
    ctype = meta.get("content_type") if preview else None
    return stream_download(request, path, meta["filename"], inline=preview, content_type=ctype)


class UrlUploadPayload(BaseModel):
    url: str
    folder: Optional[str] = None
    description: str = ""


def _filename_from_url(url: str, content_type: str | None) -> str:
    """Best-effort name: the URL's last path segment, else a probe of the type."""
    try:
        path = urlsplit(url).path
        name = os.path.basename(path)
    except ValueError:
        name = ""
    name = name.replace("%2F", "") or ""
    name = clean_name(name, 120).lstrip(".\u0085\u2028\u2029")
    if not name:
        guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
        name = "file" + (guessed or "")
    return name


@router.post("/api/public/upload_url")
async def public_upload_from_url(request: Request, payload: UrlUploadPayload):
    """Fetch a URL (through PROXY_BASE_URL) and file the bytes as a public upload.

    The server does the downloading, so no browser fetch/CORS limits apply; the
    transfer is throttled to URL_THROTTLE_MBPS for anonymous callers and left
    uncapped for a signed-in session. `folder` works like /api/public/upload.
    """
    import httpx

    ip = client_ip(request)
    check_rate_limit(ip)
    url = (payload.url or "").strip()
    if not re.match(r"^https?://\S+$", url, re.IGNORECASE):
        raise HTTPException(400, "Provide an http(s) URL")
    # Early perm check so an unpermitted upload never downloads anything.
    if payload.folder and re.fullmatch(r"[0-9a-fA-F-]{36}", str(payload.folder).strip()):
        if not _folder_gate(request, str(payload.folder).strip())["can_upload"]:
            raise HTTPException(403, "This folder is read-only")
    target = f"{settings.proxy_base_url}/{url}"

    dest = os.path.join(settings.tmp_dir, f"url_{os.getpid()}_{os.urandom(6).hex()}")
    digest = hashlib.sha256()
    written = 0
    # Anonymous callers are throttled to URL_THROTTLE_MBPS; signed-in is free.
    rate = 0 if request.session.get("auth") else settings.url_throttle_mbps * 125_000
    fname_type = ""
    imported = None
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60, read=120)) as cl:
            async with cl.stream("GET", target) as resp:
                if resp.status_code >= 400:
                    raise HTTPException(400, f"Source returned HTTP {resp.status_code}")
                cd = resp.headers.get("content-disposition", "")
                imported = re.search(
                    r"filename\*=UTF-8'([^']*)'([^;]+)|filename=\"([^\"]+)\"|filename=([^;\s]+)",
                    cd, re.I,
                )
                fname_type = resp.headers.get("content-type", "")
                loop = asyncio.get_running_loop()
                slot = 0.0
                with open(dest, "wb") as out:
                    async for chunk in resp.aiter_bytes(512 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > settings.max_file_size:
                            raise HTTPException(
                                413, f"File exceeds the {settings.max_file_size // 1024**3}GB per-file limit"
                            )
                        digest.update(chunk)
                        out.write(chunk)
                        if rate:
                            now = loop.time()
                            slot = max(slot, now) + len(chunk) / rate
                            if slot - now > 0:
                                await asyncio.sleep(min(slot - now, 5))
        file_id = digest.hexdigest()
        deduped = os.path.exists(bin_path(file_id))
        store_blob(dest, file_id)
    except HTTPException:
        if os.path.exists(dest):
            os.remove(dest)
        raise
    except (httpx.HTTPError, OSError):
        if os.path.exists(dest):
            os.remove(dest)
        raise HTTPException(400, "Could not fetch that URL through the proxy")

    def _cd_name(match: re.Match | None) -> str:
        """RFC 5987 first (`filename*=UTF-8''...`), then plain filename=."""
        if not match:
            return ""
        if match.group(1) is not None:
            from urllib.parse import unquote

            return clean_name(unquote(match.group(1)), 120)
        return clean_name(match.group(3) or match.group(2) or "", 120)

    name = _cd_name(imported) or _filename_from_url(url, fname_type)
    _, ext = os.path.splitext(name)
    ext = ext[:32] if re.fullmatch(r"\.[A-Za-z0-9._-]+", ext or "") else ""
    meta = {
        "filename": name,
        "ext": ext,
        "content_type": fname_type.split(";")[0].strip() or mimetypes.guess_type(name)[0] or "application/octet-stream",
        "size": written,
        "description": clean_name(payload.description, 200),
    }
    base = base_url(request)
    if payload.folder:
        folder_id = resolve_public_folder(
            payload.folder,
            t(lang_for(request), "unnamed_folder"),
            owner=_folder_owner(request),
        )
        validate_public_id(folder_id, "folder id")
        if not _folder_gate(request, folder_id)["can_upload"]:
            raise HTTPException(403, "This folder is read-only")
        save_entry(public_folder_dir(folder_id), file_id, meta)
        download_url = f"{base}/dl/pub/{folder_id}/{file_id}"
        return {
            "success": True,
            "folder_id": folder_id,
            "folder_name": public_folder_name(folder_id),
            "file_id": file_id,
            "filename": name,
            "description": meta["description"],
            "size_bytes": written,
            "content_type": meta["content_type"],
            "deduplicated": deduped,
            "short_url": _short_url(base, file_id, ext),
            "url": download_url,
            "download_url": download_url,
            "folder_url": f"{base}/f/{folder_id}",
            "share_url": f"{base}/f/{folder_id}",
            "folder_api_url": f"{base}/api/public/folder/{folder_id}",
            "file_api_url": f"{base}/api/public/file/{folder_id}/{file_id}",
        }
    save_entry(settings.single_dir, file_id, meta)
    download_url = f"{base}/dl/s/{file_id}"
    return {
        "success": True,
        "file_id": file_id,
        "filename": name,
        "description": meta["description"],
        "size_bytes": written,
        "content_type": meta["content_type"],
        "deduplicated": deduped,
        "short_url": _short_url(base, file_id, ext),
        "url": download_url,
        "download_url": download_url,
        "file_api_url": f"{base}/api/public/single/{file_id}",
    }


@router.get("/zip/f/{folder_id}")
async def zip_public_folder(request: Request, folder_id: str):
    """Whole public folder as a live-streamed .zip: built on the fly, never on
    disk, so nothing is deleted afterwards —the stream simply ends.
    Read-perm respected."""
    gate = _folder_gate(request, folder_id)
    if not gate["can_read"]:
        raise HTTPException(403, "This folder is upload-only")
    fdir = public_folder_dir(folder_id)
    entries = []
    for f in public_folder_files(folder_id):
        p = payload_path(f["id"], fdir, f.get("ext", ""))
        if os.path.exists(p):
            entries.append((f["name"], p))
    if not entries:
        raise HTTPException(404, "Folder is empty")
    fname = f"{clean_name(public_folder_name(folder_id), 60) or 'folder'}.zip"
    start, build = zip_stream_request(entries)
    fail: list = []
    start(fail)
    return StreamingResponse(
        build(fail),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


class FolderPermPayload(BaseModel):
    folder_id: str
    perm: str


@router.post("/api/public/folder/perm")
async def public_folder_perm(request: Request, payload: FolderPermPayload):
    """Set what non-owners may do with a public folder: readonly (list +
    download), upload (dropbox), or both. The creating session or a signed-in
    admin only."""
    meta = public_folder_meta(payload.folder_id)
    if not meta:
        raise HTTPException(404, "Folder not found")
    owner = str(meta.get("owner", "") or "")
    is_owner = (
        bool(owner)
        and owner == (request.session.get("sid") or "")
    ) or bool(request.session.get("auth"))
    if not is_owner:
        raise HTTPException(401, "Login required")
    perm = set_public_folder_perm(payload.folder_id, payload.perm)
    return {"success": True, "folder_id": payload.folder_id, "perm": perm}


async def short_link(request: Request, code: str, ext: str, preview: bool = False):
    """Short catbox-style download path at the root: /<code>.<ext>.

    The code is the shortest unique prefix of the file's sha256, so the URL is
    stable forever and safe to cache at a CDN (immutable Cache-Control) —this
    here is the host USERCONTENT_HOST points at. Public files only. The dotted
    /usercontent/<code>.<ext> path below is the same download, kept as an
    alias for links handed out earlier.

    NOTE: not under @router — create_app registers this LAST, after every
    router, so dotted literals like /llms.txt keep their exact-route
    precedence and nothing else gets shadowed.
    """
    file_id = resolve_short_code(code)
    if not file_id:
        raise HTTPException(404, "Not found")
    found = public_file_by_id(file_id)
    if found is None:
        raise HTTPException(404, "Not found")
    dirname, meta = found
    path = payload_path(file_id, dirname, meta.get("ext", ""))
    ctype = meta.get("content_type") if preview else None
    return stream_download(
        request,
        path,
        meta.get("filename", file_id),
        inline=preview,
        content_type=ctype,
        cache=True,
    )

