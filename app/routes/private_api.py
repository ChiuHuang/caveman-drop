"""Private (password / mobile-token) routes: chunk upload, files, view, delete."""

from __future__ import annotations

import html
import json
import mimetypes
import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel

from ..config import settings
from ..negotiation import wants_html
from ..storage import (
    MAX_CHUNK_BYTES,
    assemble_chunks,
    bw_pace,
    bw_record,
    bw_status,
    check_rate_limit,
    chunk_dir,
    client_ip,
    create_private_folder,
    create_share,
    delete_private_folder,
    get_private_folders,
    get_share,
    get_shares,
    private_files,
    probe_check,
    revoke_share,
    stream_download,
    tag_ip,
    tagged_threads,
    threads_for_speed,
    validate_upload_id,
)
from ..ui import page, private_panel, share_file_rows, thread_panel

router = APIRouter()


class MergePayload(BaseModel):
    upload_id: str
    filename: str
    total_chunks: int
    folder_id: Optional[str] = None


class MkdirPayload(BaseModel):
    name: str = ""


class SharePayload(BaseModel):
    mode: str


class ShareMergePayload(BaseModel):
    upload_id: str
    filename: str
    total_chunks: int
    token: str


def _check_private(request: Request) -> None:
    if not request.session.get("auth") and request.query_params.get("token") != settings.mobile_token:
        raise HTTPException(401)


@router.get("/m/{token}")
async def mobile_get(request: Request, token: str):
    if token != settings.mobile_token:
        return PlainTextResponse("Invalid mobile upload token.", status_code=403)
    base = str(request.base_url).rstrip("/")
    return PlainTextResponse(
        "CaveMan Drop mobile upload endpoint\n\n"
        f"POST a multipart/form-data field named 'file' to {base}/m/{token}\n"
        "The uploaded file is stored in the private upload area.\n"
        "For a public upload, use POST /api/public/upload instead."
    )


@router.post("/m/{token}")
async def mobile_post(request: Request, token: str, file: Optional[UploadFile] = File(None)):
    """Legacy single-file POST ??iPhone Shortcuts compatibility."""
    if token != settings.mobile_token:
        raise HTTPException(403)
    if not file or not file.filename:
        return PlainTextResponse("No file supplied.", status_code=400)
    fid = str(uuid.uuid4())
    _, ext = os.path.splitext(file.filename)
    with open(os.path.join(settings.upload_dir, fid + ext), "wb") as f:
        f.write(await file.read())
    with open(os.path.join(settings.upload_dir, fid + ".json"), "w", encoding="utf-8") as f:
        json.dump({"filename": file.filename, "ext": ext}, f)
    return PlainTextResponse(f"Uploaded: {file.filename}\nFile ID: {fid}")


@router.post("/api/probe")
async def private_probe(request: Request, probe: UploadFile = File(...)):
    """1MB speed probe for the private uploader."""
    import time as _time

    _check_private(request)
    ip = client_ip(request)
    probe_check(ip)
    data = await probe.read()
    await probe.close()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, "Probe too large")
    elapsed = max(_time.time() - getattr(request.state, "t0", _time.time()), 0.001)
    threads = threads_for_speed(len(data) / elapsed)
    tag_ip(ip, threads)
    return {"threads": threads, "you": ip}


@router.post("/api/folders")
async def create_folder(request: Request, payload: MkdirPayload):
    if not request.session.get("auth"):
        raise HTTPException(401)
    fid, meta = create_private_folder(payload.name)
    return {"success": True, "folder_id": fid, "name": meta["name"]}


@router.get("/api/folders")
async def list_folders(request: Request):
    if not request.session.get("auth"):
        if wants_html(request):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    folders = get_private_folders()
    counts: dict[str, int] = {}
    for f in private_files():
        if f.get("folder"):
            counts[f["folder"]] = counts.get(f["folder"], 0) + 1
    from ..storage import get_shares as _gs

    shares = _gs()
    base = str(request.base_url).rstrip("/")
    if wants_html(request):
        return RedirectResponse("/", status_code=303)
    return {
        "folders": [
            {
                "id": fid,
                "name": m.get("name", ""),
                "ctime": m.get("ctime", 0),
                "count": counts.get(fid, 0),
                "shares": [
                    {"token": t, "mode": s["mode"], "url": f"{base}/s/{t}"}
                    for t, s in shares.items()
                    if s.get("folder_id") == fid
                ],
            }
            for fid, m in folders.items()
        ]
    }


@router.get("/deldir/{folder_id}")
async def delete_folder(request: Request, folder_id: str):
    if not request.session.get("auth"):
        if wants_html(request):
            return RedirectResponse(url="/login", status_code=303)
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    n = delete_private_folder(folder_id)
    if wants_html(request):
        return RedirectResponse(url="/", status_code=303)
    return {"success": True, "deleted_files": n}


@router.post("/api/folders/{folder_id}/share")
async def share_folder(request: Request, folder_id: str, payload: SharePayload):
    if not request.session.get("auth"):
        raise HTTPException(401)
    token, meta = create_share(folder_id, payload.mode)
    base = str(request.base_url).rstrip("/")
    return {"success": True, "token": token, "mode": meta["mode"], "url": f"{base}/s/{token}"}


@router.post("/api/share/revoke")
async def unshare(request: Request, payload: dict):
    if not request.session.get("auth"):
        raise HTTPException(401)
    ok = revoke_share(str(payload.get("token", "")))
    if not ok:
        raise HTTPException(404, "Share not found")
    return {"success": True}


@router.post("/api/share/merge_chunks")
async def share_merge_chunks(request: Request, payload: ShareMergePayload):
    """Upload into a shared private folder via an upload-mode link."""
    import mimetypes as _mime
    import os as _os

    share = get_share(payload.token)
    if not share:
        raise HTTPException(404, "Share not found")
    if share.get("mode") != "upload":
        raise HTTPException(403, "This link is view-only")
    folder_id = share["folder_id"]
    if folder_id not in get_private_folders():
        raise HTTPException(404, "Folder not found")
    ip = client_ip(request)
    check_rate_limit(ip)
    validate_upload_id(payload.upload_id)
    fid = str(uuid.uuid4())
    _, ext = _os.path.splitext(payload.filename)
    dest = _os.path.join(settings.upload_dir, fid + ext)
    cdir = _os.path.join(settings.tmp_dir, f"pub_{payload.upload_id}")
    written = assemble_chunks(cdir, dest, payload.total_chunks, None)
    content_type = _mime.guess_type(payload.filename)[0] or "application/octet-stream"
    with open(_os.path.join(settings.upload_dir, fid + ".json"), "w", encoding="utf-8") as f:
        json.dump({"filename": payload.filename, "ext": ext, "content_type": content_type, "folder": folder_id}, f)
    bw_record(ip, None, written)
    base = str(request.base_url).rstrip("/")
    download_url = f"{base}/dl/sh/{payload.token}/{fid}"
    return {
        "success": True,
        "file_id": fid,
        "filename": payload.filename,
        "size_bytes": written,
        "content_type": content_type,
        "url": download_url,
        "download_url": download_url,
        "file_api_url": download_url,
    }


@router.get("/dl/sh/{token}/{file_id}")
async def share_download(request: Request, token: str, file_id: str, preview: bool = False):
    import mimetypes as _mime
    import os as _os

    share = get_share(token)
    if not share:
        raise HTTPException(404)
    jp = _os.path.join(settings.upload_dir, file_id + ".json")
    if not _os.path.exists(jp):
        raise HTTPException(404)
    with open(jp, encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("folder") != share["folder_id"]:
        raise HTTPException(404)
    path = _os.path.join(settings.upload_dir, file_id + meta.get("ext", ""))
    ctype = meta.get("content_type") or _mime.guess_type(meta.get("filename", ""))[0] if preview else None
    return stream_download(request, path, meta["filename"], inline=preview, content_type=ctype)


@router.get("/s/{token}")
async def share_page(request: Request, token: str):
    """Shared private folder: view-only or upload-capable, no login needed."""
    from ..ui import page as _page

    share = get_share(token)
    if not share:
        if wants_html(request):
            return HTMLResponse(_page("找不到", '<mdui-card class="card-pad"><p>連結無效或已被取消。</p></mdui-card>'), status_code=404)
        return PlainTextResponse("Share not found.", status_code=404)
    folders = get_private_folders()
    meta = folders.get(share["folder_id"])
    if not meta:
        if wants_html(request):
            return HTMLResponse(_page("找不到", '<mdui-card class="card-pad"><p>資料夾已刪除。</p></mdui-card>'), status_code=404)
        return PlainTextResponse("Folder not found.", status_code=404)
    name = meta.get("name", "")
    can_upload = share.get("mode") == "upload"
    files = [f for f in private_files() if f.get("folder") == share["folder_id"]]
    base = str(request.base_url).rstrip("/")
    if not wants_html(request):
        lines = [f"Shared folder: {name}", f"mode: {share['mode']}", f"files: {len(files)}", ""]
        for f in files:
            lines += [f"  {f['name']}", f"    size: {f['bytes']}", f"    url: {base}/dl/sh/{token}/{f['id']}"]
        if can_upload:
            lines += ["", f"Upload: POST {base}/api/public/chunk parts, then POST {base}/api/share/merge_chunks with token"]
        return PlainTextResponse("\n".join(lines))
    for f in files:
        f["bytes"] = f.get("bytes", 0)
    up_card = f"""
          <mdui-card variant="outlined" class="card-pad">
            <h2>上傳到此資料夾</h2>
            <form action="/api/public/chunk" method="post" data-chunked data-merge="/api/share/merge_chunks" data-public="1" data-probe="/api/public/probe">
              <input type="hidden" name="token" value="{html.escape(token)}">
              <div class="form-row">
                <input type="file" name="file" required>
                <mdui-button type="submit">上傳</mdui-button>
              </div>
              {thread_panel()}
            </form>
            <div data-upload-result></div>
          </mdui-card>""" if can_upload else ""
    return HTMLResponse(
        _page(
            name,
            f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(name)}</h1>
          <p>分享資料夾 · {len(files)} 個檔案 · {"可上傳" if can_upload else "僅檢視"}</p>
        </mdui-card>
        <div class="stack">
          <mdui-card variant="outlined" class="card-pad">
            <h2>檔案（{len(files)}）</h2>
            {share_file_rows(files, token, base)}
          </mdui-card>
          {up_card}
        </div>""",
            active="home",
        )
    )


@router.post("/api/upload_chunk")
async def upload_chunk(
    request: Request,
    file_chunk: UploadFile = File(...),
    upload_id: str = Form(...),
    index: int = Form(...),
    filename: str = Form(...),
):
    _check_private(request)
    ip = client_ip(request)
    authed = bool(request.session.get("auth"))
    validate_upload_id(upload_id)
    if index < 0 or index >= settings.max_chunked_parts:
        raise HTTPException(400, "Chunk index out of range")
    data = await file_chunk.read()
    await file_chunk.close()
    if len(data) > MAX_CHUNK_BYTES:
        raise HTTPException(413, "Chunk too large")
    cdir = chunk_dir("priv", upload_id)
    with open(os.path.join(cdir, f"part_{index}"), "wb") as f:
        f.write(data)
    if authed:
        return {
            "ok": True, "throttled": False, "threads": 16,
            "throttle_mbps": None, "exempt": True,
        }
    bw_record(ip, None, len(data))
    status = bw_status(ip)
    await bw_pace(ip, len(data), status["throttle_mbps"])
    status["threads_tagged"] = tagged_threads(ip)
    return {"ok": True, **status}


@router.post("/api/merge_chunks")
async def merge_chunks(request: Request, payload: MergePayload):
    _check_private(request)
    validate_upload_id(payload.upload_id)
    folder_id = payload.folder_id
    if folder_id:
        folders = get_private_folders()
        if folder_id not in folders:
            raise HTTPException(404, "Folder not found")
    fid = str(uuid.uuid4())
    _, ext = os.path.splitext(payload.filename)
    final_path = os.path.join(settings.upload_dir, fid + ext)
    cdir = os.path.join(settings.tmp_dir, f"priv_{payload.upload_id}")
    assemble_chunks(cdir, final_path, payload.total_chunks, None)
    with open(os.path.join(settings.upload_dir, fid + ".json"), "w", encoding="utf-8") as f:
        json.dump({"filename": payload.filename, "ext": ext, "folder": folder_id}, f)
    return {"success": True, "file_id": fid}


@router.get("/api/files")
async def api_files(request: Request):
    if not request.session.get("auth"):
        if wants_html(request):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    files = private_files()
    if not wants_html(request):
        return {"files": files}
    base = str(request.base_url).rstrip("/")
    return HTMLResponse(
        page(
            "私人檔案",
            f"""<mdui-card variant="filled" class="card-pad hero">
          <h1>私人雲端</h1>
          <p><a href="/">回私人模式首頁</a></p>
        </mdui-card>
        <div class="stack">{private_panel(files, base, get_private_folders(), get_shares())}</div>""",
            active="home",
            authed=True,
        )
    )


@router.get("/dl/{file_id}")
async def download(request: Request, file_id: str, preview: bool = False):
    jp = os.path.join(settings.upload_dir, file_id + ".json")
    if not os.path.exists(jp):
        raise HTTPException(404)
    with open(jp, encoding="utf-8") as f:
        meta = json.load(f)
    path = os.path.join(settings.upload_dir, file_id + meta.get("ext", ""))
    ctype = mimetypes.guess_type(meta.get("filename", ""))[0] if preview else None
    return stream_download(request, path, meta["filename"], inline=preview, content_type=ctype)


@router.get("/view/{file_id}")
async def view_file(file_id: str):
    jp = os.path.join(settings.upload_dir, file_id + ".json")
    if not os.path.exists(jp):
        raise HTTPException(404)
    with open(jp, encoding="utf-8") as f:
        meta = json.load(f)
    path = os.path.join(settings.upload_dir, file_id + meta.get("ext", ""))
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path, filename=meta["filename"])


@router.get("/del/{file_id}")
async def delete_file(request: Request, file_id: str):
    if not request.session.get("auth"):
        if wants_html(request):
            return RedirectResponse(url="/login", status_code=303)
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    jp = os.path.join(settings.upload_dir, file_id + ".json")
    if os.path.exists(jp):
        with open(jp, encoding="utf-8") as f:
            meta = json.load(f)
        p = os.path.join(settings.upload_dir, file_id + meta.get("ext", ""))
        if os.path.exists(p):
            os.remove(p)
        os.remove(jp)
    if wants_html(request):
        return RedirectResponse(url="/", status_code=303)
    return {"success": True}


@router.get("/SF-Pro.ttf")
async def font():
    if os.path.exists("SF-Pro.ttf"):
        return FileResponse("SF-Pro.ttf")
    raise HTTPException(404)
