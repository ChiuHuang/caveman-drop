"""Filesystem storage helpers shared by all routes."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import time
from collections import defaultdict
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from .config import settings

PUBLIC_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")

_upload_log: dict[str, list[float]] = defaultdict(list)
_public_folder_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def check_rate_limit(ip: str) -> None:
    now = time.time()
    log = _upload_log[ip]
    while log and now - log[0] > settings.rate_limit_window:
        log.pop(0)
    if len(log) >= settings.rate_limit_max_uploads:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded: max {settings.rate_limit_max_uploads} "
                f"uploads/hour per IP"
            ),
        )
    log.append(now)


def validate_public_id(value: str, label: str = "id") -> None:
    if not PUBLIC_ID_RE.fullmatch(value or ""):
        raise HTTPException(400, f"Invalid public {label}")


def public_folder_dir(folder_id: str) -> str:
    validate_public_id(folder_id, "folder id")
    return os.path.join(settings.public_dir, folder_id)


def public_folder_files(folder_id: str) -> list[dict[str, Any]]:
    d = public_folder_dir(folder_id)
    out: list[dict[str, Any]] = []
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        fid = fn[:-5]
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                meta = json.load(f)
            path = os.path.join(d, fid + meta.get("ext", ""))
            if not os.path.exists(path):
                continue
            out.append(
                {
                    "id": fid,
                    "name": meta["filename"],
                    "size": os.path.getsize(path),
                    "ctime": meta.get("ctime", os.path.getctime(path)),
                    "content_type": meta.get(
                        "content_type",
                        mimetypes.guess_type(meta.get("filename", ""))[0]
                        or "application/octet-stream",
                    ),
                }
            )
        except Exception:
            continue
    out.sort(key=lambda x: x["ctime"], reverse=True)
    return out


def private_files() -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    if not os.path.isdir(settings.upload_dir):
        return files
    for fn in os.listdir(settings.upload_dir):
        if not fn.endswith(".json"):
            continue
        fid = fn[:-5]
        try:
            with open(os.path.join(settings.upload_dir, fn), encoding="utf-8") as f:
                meta = json.load(f)
            path = os.path.join(settings.upload_dir, fid + meta.get("ext", ""))
            if not os.path.exists(path):
                continue
            size = os.path.getsize(path)
            files.append(
                {
                    "id": fid,
                    "name": meta["filename"],
                    "size": size // 1024,
                    "bytes": size,
                    "ctime": os.path.getctime(path),
                }
            )
        except Exception:
            continue
    files.sort(key=lambda x: x["ctime"], reverse=True)
    return files


def stream_download(request: Request, path: str, fname: str) -> StreamingResponse:
    if not os.path.exists(path):
        raise HTTPException(404)
    file_size = os.path.getsize(path)
    rng = request.headers.get("range")

    if not rng:
        def streamer():
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(512 * 1024)
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            streamer(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{fname}"',
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
            },
        )

    try:
        s, e = rng.replace("bytes=", "").split("-")
        start = int(s)
        end = int(e) if e else file_size - 1
    except Exception:
        raise HTTPException(400)
    end = min(end, file_size - 1)
    length = end - start + 1

    def ranged():
        with open(path, "rb") as f:
            f.seek(start)
            rem = length
            while rem > 0:
                chunk = f.read(min(512 * 1024, rem))
                if not chunk:
                    break
                rem -= len(chunk)
                yield chunk

    return StreamingResponse(
        ranged(),
        status_code=206,
        media_type="application/octet-stream",
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Disposition": f'attachment; filename="{fname}"',
        },
    )


def folder_lock(folder_id: str) -> asyncio.Lock:
    return _public_folder_locks[folder_id]
