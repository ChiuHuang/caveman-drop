"""Private (password / mobile-token) routes: chunk upload, files, view, delete."""

from __future__ import annotations

import html
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
    bin_path,
    bw_pace,
    bw_record,
    bw_status,
    check_rate_limit,
    chunk_dir,
    clean_name,
    client_ip,
    create_private_folder,
    create_share,
    delete_file_entry,
    delete_private_folder,
    delete_public_folder,
    entry_meta,
    find_public_entry_dir,
    forget_short_code,
    get_private_folders,
    get_share,
    get_shares,
    listdir_safe,
    move_entry,
    payload_path,
    private_files,
    probe_check,
    public_files,
    public_folder_files,
    public_folder_list,
    rename_file_entry,
    rename_private_folder,
    rename_public_folder,
    revoke_share,
    save_entry,
    speed_probe,
    store_blob,
    stream_download,
    tag_ip,
    tagged_threads,
    validate_upload_id,
)
from ..i18n import lang_for, t
from ..ui import drive_panel, page, share_file_rows, thread_panel
from ..auth import authed, query_auth_ok
from ..urls import base_url

router = APIRouter()


class MergePayload(BaseModel):
    upload_id: str
    filename: str
    total_chunks: int
    folder_id: Optional[str] = None
    description: str = ""


class MkdirPayload(BaseModel):
    name: str = ""


class RenamePayload(BaseModel):
    folder_id: str
    name: str = ""


class FileRenamePayload(BaseModel):
    file_id: str
    name: str = ""
    folder_id: Optional[str] = None


class SharePayload(BaseModel):
    mode: str


class ShareMergePayload(BaseModel):
    upload_id: str
    filename: str
    total_chunks: int
    token: str


class MovePayload(BaseModel):
    file_id: str
    folder_id: Optional[str] = None
    from_folder_id: Optional[str] = None


def _need_admin(request: Request) -> None:
    if request.session.get("auth"):
        return
    if not query_auth_ok(request, raising=wants_html(request)):
        raise HTTPException(401, "Login required")


def _check_private(request: Request) -> None:
    if request.session.get("auth") or request.query_params.get("token") == settings.mobile_token:
        return
    if not query_auth_ok(request, raising=False):
        raise HTTPException(401)




@router.get("/m/{token}")
async def mobile_get(request: Request, token: str):
    if token != settings.mobile_token:
        return PlainTextResponse("Invalid mobile upload token.", status_code=403)
    base = base_url(request)
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
    _, ext = os.path.splitext(file.filename)
    tmp = os.path.join(settings.tmp_dir, f"up_{uuid.uuid4()}")
    with open(tmp, "wb") as f:
        f.write(await file.read())
    fid = store_blob(tmp)
    save_entry(
        settings.upload_dir,
        fid,
        {
            "filename": file.filename,
            "ext": ext,
            "content_type": mimetypes.guess_type(file.filename)[0] or "application/octet-stream",
            "size": os.path.getsize(bin_path(fid)),
        },
    )
    return PlainTextResponse(f"Uploaded: {file.filename}\nFile ID: {fid}")


@router.post("/api/probe")
async def private_probe(request: Request, probe: UploadFile = File(...), ms: Optional[str] = Form(None)):
    """Speed probe for the private uploader."""
    _check_private(request)
    ip = client_ip(request)
    probe_check(ip)
    data = await probe.read()
    await probe.close()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Probe too large")
    threads, bps = speed_probe(len(data), request, ms)
    tag_ip(ip, threads)
    return {"threads": threads, "mbps": round(bps * 8 / 1_000_000, 2), "you": ip}


@router.post("/api/folders")
async def create_folder(request: Request, payload: MkdirPayload):
    if not authed(request):
        raise HTTPException(401)
    fid, meta = create_private_folder(payload.name, t(lang_for(request), "unnamed_folder"))
    return {"success": True, "folder_id": fid, "name": meta["name"]}


@router.post("/api/folders/rename")
async def rename_folder(request: Request, payload: RenamePayload):
    """Change a private folder's name. The id, the files and the share links stay."""
    _need_admin(request)
    name = rename_private_folder(
        payload.folder_id, payload.name, t(lang_for(request), "unnamed_folder")
    )
    return {"success": True, "folder_id": payload.folder_id, "name": name}


@router.post("/api/public/folder/rename")
async def rename_pub_folder(request: Request, payload: RenamePayload):
    """Change a public folder's name. Its URL does not change."""
    _need_admin(request)
    name = rename_public_folder(
        payload.folder_id, payload.name, t(lang_for(request), "unnamed_folder")
    )
    return {"success": True, "folder_id": payload.folder_id, "name": name}


@router.post("/api/files/rename")
async def rename_private_file(request: Request, payload: FileRenamePayload):
    """Change a private file's display name. id, bytes and links stay."""
    _need_admin(request)
    name = rename_file_entry(settings.upload_dir, payload.file_id, payload.name)
    return {"success": True, "file_id": payload.file_id, "name": name}


@router.post("/api/public/file/rename")
async def rename_pub_file(request: Request, payload: FileRenamePayload):
    """Change a public file's display name. id, bytes and links stay."""
    _need_admin(request)
    d = find_public_entry_dir(payload.file_id, payload.folder_id or "")
    name = rename_file_entry(d, payload.file_id, payload.name)
    return {"success": True, "file_id": payload.file_id, "name": name}


@router.get("/api/folders")
async def list_folders(request: Request):
    if not authed(request):
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
    base = base_url(request)
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


@router.api_route("/deldir/{folder_id}", methods=["GET", "POST"])
async def delete_folder(request: Request, folder_id: str):
    """Delete a private folder. POST lets the drive stay on the folder it is showing."""
    if not authed(request):
        if wants_html(request):
            return RedirectResponse(url="/login", status_code=303)
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    n = delete_private_folder(folder_id)
    if wants_html(request):
        return RedirectResponse(url="/", status_code=303)
    return {"success": True, "deleted_files": n}


@router.post("/api/folders/{folder_id}/share")
async def share_folder(request: Request, folder_id: str, payload: SharePayload):
    if not authed(request):
        raise HTTPException(401)
    token, meta = create_share(folder_id, payload.mode)
    base = base_url(request)
    return {"success": True, "token": token, "mode": meta["mode"], "url": f"{base}/s/{token}"}


@router.post("/api/share/revoke")
async def unshare(request: Request, payload: dict):
    if not authed(request):
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
    _, ext = _os.path.splitext(payload.filename)
    cdir = _os.path.join(settings.tmp_dir, f"pub_{payload.upload_id}")
    fid, written = assemble_chunks(cdir, payload.total_chunks, None)
    content_type = _mime.guess_type(payload.filename)[0] or "application/octet-stream"
    save_entry(
        settings.upload_dir,
        fid,
        {"filename": payload.filename, "ext": ext, "content_type": content_type,
         "folder": folder_id, "size": written},
    )
    bw_record(ip, None, written)
    base = base_url(request)
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

    share = get_share(token)
    if not share:
        raise HTTPException(404)
    meta = entry_meta(settings.upload_dir, file_id)
    if meta is None:
        raise HTTPException(404)
    if meta.get("folder") != share["folder_id"]:
        raise HTTPException(404)
    path = payload_path(file_id, settings.upload_dir, meta.get("ext", ""))
    ctype = meta.get("content_type") or _mime.guess_type(meta["filename"])[0] if preview else None
    return stream_download(request, path, meta["filename"], inline=preview, content_type=ctype)


@router.get("/s/{token}")
async def share_page(request: Request, token: str):
    """Shared private folder: view-only or upload-capable, no login needed."""
    from ..ui import page as _page

    lang = lang_for(request)
    share = get_share(token)
    if not share:
        if wants_html(request):
            body = '<mdui-card class="card-pad"><p>' + html.escape(t(lang, "share_invalid")) + "</p></mdui-card>"
            return HTMLResponse(_page(t(lang, "not_found"), body, lang=lang), status_code=404)
        return PlainTextResponse("Share not found.", status_code=404)
    folders = get_private_folders()
    meta = folders.get(share["folder_id"])
    if not meta:
        if wants_html(request):
            body = '<mdui-card class="card-pad"><p>' + html.escape(t(lang, "share_gone")) + "</p></mdui-card>"
            return HTMLResponse(_page(t(lang, "not_found"), body, lang=lang), status_code=404)
        return PlainTextResponse("Folder not found.", status_code=404)
    name = meta.get("name", "")
    can_upload = share.get("mode") == "upload"
    files = [f for f in private_files() if f.get("folder") == share["folder_id"]]
    base = base_url(request)
    if not wants_html(request):
        lines = [f"Shared folder: {name}", f"mode: {share['mode']}", f"files: {len(files)}", ""]
        for f in files:
            lines += [f"  {f['name']}", f"    size: {f['bytes']}", f"    url: {base}/dl/sh/{token}/{f['id']}"]
        if can_upload:
            lines += ["", f"Upload: POST {base}/api/public/chunk parts, then POST {base}/api/share/merge_chunks with token"]
        return PlainTextResponse("\n".join(lines))
    for f in files:
        f["bytes"] = f.get("bytes", 0)
    mode = t(lang, "share_can_upload" if can_upload else "share_view_only")
    up_card = f"""
          <mdui-card variant="outlined" class="card-pad">
            <h2>{html.escape(t(lang, "share_folder_h"))}</h2>
            <form action="/api/public/chunk" method="post" data-chunked data-merge="/api/share/merge_chunks" data-public="1">
              <input type="hidden" name="token" value="{html.escape(token)}">
              <div class="form-row">
                <input type="file" name="file" multiple required>
                <mdui-button type="submit" icon="cloud_upload">{html.escape(t(lang, "btn_upload"))}</mdui-button>
              </div>
              {thread_panel(lang)}
            </form>
            <div data-upload-result></div>
          </mdui-card>""" if can_upload else ""
    return HTMLResponse(
        _page(
            name,
            f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(name)}</h1>
          <p>{html.escape(t(lang, "share_meta", n=len(files), mode=mode))}</p>
        </mdui-card>
        <div class="stack">
          <mdui-card variant="outlined" class="card-pad">
            <h2>{html.escape(t(lang, "files_h", n=len(files)))}</h2>
            {share_file_rows(lang, files, token, base)}
          </mdui-card>
          {up_card}
        </div>""",
            active="home",
            lang=lang,
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
    cdir = os.path.join(settings.tmp_dir, f"priv_{payload.upload_id}")
    fid, written = assemble_chunks(cdir, payload.total_chunks, None)
    _, ext = os.path.splitext(payload.filename)
    save_entry(
        settings.upload_dir,
        fid,
        {
            "filename": payload.filename,
            "ext": ext,
            "folder": folder_id,
            "description": clean_name(payload.description, 200),
            "content_type": mimetypes.guess_type(payload.filename)[0] or "application/octet-stream",
            "size": written,
        },
    )
    return {"success": True, "file_id": fid, "size_bytes": written}


@router.get("/api/files")
async def api_files(request: Request):
    if not authed(request):
        if wants_html(request):
            return RedirectResponse("/login", status_code=303)
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    files = private_files()
    if not wants_html(request):
        return {"files": files}
    base = base_url(request)
    lang = lang_for(request)
    return HTMLResponse(
        page(
            t(lang, "private_cloud_h"),
            f"""<mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(t(lang, "private_cloud_h"))}</h1>
          <p><a href="/">{html.escape(t(lang, "back_home"))}</a></p>
        </mdui-card>
        <div class="stack">{drive_panel(
            lang, files, base, get_private_folders(), get_shares(),
        )}</div>""",
            active="home",
            authed=True,
            lang=lang,
        )
    )


@router.post("/api/files/move")
async def move_private_file(request: Request, payload: MovePayload):
    """Drag and drop: move a private file into another folder (or out of one)."""
    _need_admin(request)
    folder_id = payload.folder_id or None
    if folder_id and folder_id not in get_private_folders():
        raise HTTPException(404, "Folder not found")
    if not move_entry(settings.upload_dir, payload.file_id, folder_id):
        raise HTTPException(404, "File not found")
    return {"success": True, "file_id": payload.file_id, "folder_id": folder_id}


@router.get("/api/public/files")
async def list_all_public(request: Request):
    """Admin view: every public file and folder in one list."""
    _need_admin(request)
    return {
        "files": public_files(),
        "folders": public_folder_list(t(lang_for(request), "unnamed_folder")),
    }


@router.post("/api/public/move")
async def move_public_file(request: Request, payload: MovePayload):
    """Drag and drop: move a public file to another public folder.

    The same bytes can sit in more than one public folder, so the source folder
    comes from the row that was dragged; without it we fall back to a search.
    """
    _need_admin(request)
    src = ""
    if payload.from_folder_id:
        cand = os.path.join(settings.public_dir, payload.from_folder_id)
        if os.path.isdir(cand) and os.path.exists(os.path.join(cand, payload.file_id + ".json")):
            src = cand
    if not src:
        for d in listdir_safe(settings.public_dir):
            cand = os.path.join(settings.public_dir, d)
            if os.path.isdir(cand) and os.path.exists(os.path.join(cand, payload.file_id + ".json")):
                src = cand
                break
    if not src and os.path.exists(os.path.join(settings.single_dir, payload.file_id + ".json")):
        src = settings.single_dir
    if not src:
        raise HTTPException(404, "File not found")
    target = settings.single_dir
    if payload.folder_id:
        cand = os.path.join(settings.public_dir, payload.folder_id)
        if not os.path.isdir(cand):
            raise HTTPException(404, "Folder not found")
        target = cand
    meta = entry_meta(src, payload.file_id)
    if meta is None:
        raise HTTPException(404, "File not found")
    meta.pop("size", None)
    meta.pop("ctime", None)
    save_entry(target, payload.file_id, meta)
    try:
        os.remove(os.path.join(src, payload.file_id + ".json"))
    except OSError:
        pass
    return {"success": True, "file_id": payload.file_id, "folder_id": payload.folder_id or ""}


@router.post("/delpub/{file_id}")
async def delete_public_file(request: Request, file_id: str):
    """Remove this file everywhere it is shared publicly (bytes stay if private)."""
    _need_admin(request)
    n = 0
    roots = [settings.single_dir] + [
        os.path.join(settings.public_dir, d) for d in listdir_safe(settings.public_dir)
    ]
    for root in roots:
        if os.path.exists(os.path.join(root, file_id + ".json")) and delete_file_entry(root, file_id):
            n += 1
    if n:
        forget_short_code(file_id)
        return {"success": True, "deleted": n}
    raise HTTPException(404, "File not found")


@router.post("/delpubdir/{folder_id}")
async def delpub_folder(request: Request, folder_id: str):
    _need_admin(request)
    for f in public_folder_files(folder_id):
        forget_short_code(f["id"])
    n = delete_public_folder(folder_id)
    return {"success": True, "deleted_files": n}


@router.get("/dl/{file_id}")
async def download(request: Request, file_id: str, preview: bool = False):
    meta = entry_meta(settings.upload_dir, file_id)
    if meta is None:
        raise HTTPException(404)
    path = payload_path(file_id, settings.upload_dir, meta.get("ext", ""))
    ctype = meta.get("content_type") or mimetypes.guess_type(meta.get("filename", ""))[0] if preview else None
    return stream_download(request, path, meta["filename"], inline=preview, content_type=ctype)


@router.get("/view/{file_id}")
async def view_file(file_id: str):
    meta = entry_meta(settings.upload_dir, file_id)
    if meta is None:
        raise HTTPException(404)
    path = payload_path(file_id, settings.upload_dir, meta.get("ext", ""))
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path, filename=meta["filename"])


@router.api_route("/del/{file_id}", methods=["GET", "POST"])
async def delete_file(request: Request, file_id: str):
    if not authed(request):
        if wants_html(request):
            return RedirectResponse(url="/login", status_code=303)
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    delete_file_entry(settings.upload_dir, file_id)
    if wants_html(request):
        return RedirectResponse(url="/", status_code=303)
    return {"success": True}


@router.get("/SF-Pro.ttf")
async def font():
    if os.path.exists("SF-Pro.ttf"):
        return FileResponse("SF-Pro.ttf")
    raise HTTPException(404)
