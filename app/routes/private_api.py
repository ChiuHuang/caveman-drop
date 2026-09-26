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
    chunk_dir,
    client_ip,
    create_private_folder,
    delete_private_folder,
    get_private_folders,
    private_files,
    probe_check,
    stream_download,
    tag_ip,
    tagged_threads,
    threads_for_speed,
    validate_upload_id,
)
from ..ui import page, private_panel

router = APIRouter()


class MergePayload(BaseModel):
    upload_id: str
    filename: str
    total_chunks: int
    folder_id: Optional[str] = None


class MkdirPayload(BaseModel):
    name: str = ""


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
    if wants_html(request):
        return RedirectResponse("/", status_code=303)
    return {
        "folders": [
            {"id": fid, "name": m.get("name", ""), "ctime": m.get("ctime", 0), "count": counts.get(fid, 0)}
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
        <div class="stack">{private_panel(files, base, get_private_folders())}</div>""",
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
