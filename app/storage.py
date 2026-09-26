"""Filesystem storage helpers shared by all routes."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from .config import settings

PUBLIC_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")

_upload_log: dict[str, list[float]] = defaultdict(list)
_public_folder_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# Bandwidth accounting (sliding windows) + chunk helpers.
_bw_bytes: dict[str, deque] = defaultdict(deque)  # "ip:<ip>" / "folder:<id>" -> [(ts, bytes)]
_bw_folders: dict[str, deque] = defaultdict(deque)  # ip -> [(ts, folder_id)]
_pace_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_pace_next: dict[str, float] = {}
MAX_CHUNK_BYTES = 32 * 1024 * 1024


def _bw_window() -> float:
    return float(settings.bw_window_seconds)


def _prune(dq: deque, now: float) -> None:
    window = _bw_window()
    while dq and now - dq[0][0] > window:
        dq.popleft()


def bw_record(ip: str, folder_id: str | None, nbytes: int) -> None:
    """Record uploaded bytes for an IP (and folder, if known)."""
    now = time.time()
    dq = _bw_bytes[f"ip:{ip}"]
    dq.append((now, nbytes))
    _prune(dq, now)
    if folder_id:
        fdq = _bw_bytes[f"folder:{folder_id}"]
        fdq.append((now, nbytes))
        _prune(fdq, now)
        touch = _bw_folders[ip]
        touch.append((now, folder_id))
        _prune(touch, now)


def bw_total(key: str) -> int:
    now = time.time()
    dq = _bw_bytes[key]
    _prune(dq, now)
    return sum(b for _, b in dq)


def client_ip(request: Request) -> str:
    """Real client IP: CF-Connecting-IP, else X-Forwarded-For, else peer."""
    cf = (request.headers.get("cf-connecting-ip") or "").strip()
    if cf:
        return cf.split(",")[0].strip()
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def throttle_mbps_for(ip_bytes: int) -> int | None:
    """90 past the soft cap, -10 per extra GB, floor 40."""
    if ip_bytes <= settings.bw_ip_soft_bytes:
        return None
    step = ip_bytes // (settings.bw_tier_gb * 1024**3)
    mbps = settings.throttle_max_mbps - step * settings.bw_tier_mbps
    return max(int(mbps), settings.throttle_min_mbps)


def bw_status(ip: str, folder_id: str | None = None) -> dict[str, Any]:
    """Bandwidth verdict: full speed, or throttled with a target Mbps."""
    ip_b = bw_total(f"ip:{ip}")
    folder_b = bw_total(f"folder:{folder_id}") if folder_id else 0
    now = time.time()
    touch = _bw_folders[ip]
    _prune(touch, now)
    folders = len({f for _, f in touch})
    mbps = throttle_mbps_for(ip_b)
    if folders > settings.bw_folders_per_window and mbps is None:
        mbps = settings.throttle_max_mbps
    if folder_b > settings.bw_folder_hard_bytes:
        mbps = settings.throttle_min_mbps if mbps is None else min(mbps, settings.throttle_min_mbps)
    throttled = mbps is not None
    return {
        "throttled": throttled,
        "throttle_mbps": mbps,
        "threads": 16,
        "ip_bytes_per_min": ip_b,
        "folder_bytes_per_min": folder_b,
        "folders_per_min": folders,
    }


async def bw_pace(ip: str, nbytes: int, mbps: int | None) -> None:
    """Cap aggregate throughput at mbps via a shared per-IP reservation queue."""
    if not mbps or nbytes <= 0:
        return
    rate = mbps * 1_000_000 / 8
    lock = _pace_locks[ip]
    async with lock:
        now = asyncio.get_running_loop().time()
        slot = max(_pace_next.get(ip, now), now) + nbytes / rate
        if len(_pace_next) > 10000:
            _pace_next.clear()
        _pace_next[ip] = slot
        delay = slot - now
    if delay > 0:
        await asyncio.sleep(delay)


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


def validate_upload_id(value: str) -> None:
    if not PUBLIC_ID_RE.fullmatch(value or ""):
        raise HTTPException(400, "Invalid upload id")


def chunk_dir(prefix: str, upload_id: str) -> str:
    """Scratch dir for one chunked upload."""
    validate_upload_id(upload_id)
    if not re.fullmatch(r"[a-z]+", prefix or ""):
        raise HTTPException(400, "Invalid chunk prefix")
    d = os.path.join(settings.tmp_dir, f"{prefix}_{upload_id}")
    os.makedirs(d, exist_ok=True)
    return d


def assemble_chunks(chunk_dirname: str, dest: str, total_chunks: int, max_bytes: int | None) -> int:
    """Concatenate part_0..N into dest, then clean up. None = no size cap."""
    limit = settings.max_chunked_parts
    if not 1 <= total_chunks <= limit:
        raise HTTPException(400, f"total_chunks must be 1..{limit}")
    written = 0
    try:
        with open(dest, "wb") as out:
            for i in range(total_chunks):
                part = os.path.join(chunk_dirname, f"part_{i}")
                if not os.path.exists(part):
                    raise HTTPException(400, f"Missing chunk {i}")
                with open(part, "rb") as p:
                    while True:
                        c = p.read(1024 * 1024)
                        if not c:
                            break
                        written += len(c)
                        if max_bytes is not None and written > max_bytes:
                            raise HTTPException(413, "File exceeds the size limit")
                        out.write(c)
    except HTTPException:
        if os.path.exists(dest):
            os.remove(dest)
        raise
    for i in range(total_chunks):
        try:
            os.remove(os.path.join(chunk_dirname, f"part_{i}"))
        except OSError:
            pass
    try:
        os.rmdir(chunk_dirname)
    except OSError:
        pass
    return written


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


def stream_download(
    request: Request,
    path: str,
    fname: str,
    inline: bool = False,
    content_type: str | None = None,
) -> StreamingResponse:
    """Range-aware download. `inline=True` renders in-browser (preview)."""
    if not os.path.exists(path):
        raise HTTPException(404)
    file_size = os.path.getsize(path)
    media = content_type or "application/octet-stream"
    disposition = ("inline" if inline else "attachment") + f'; filename="{fname}"'
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
            media_type=media,
            headers={
                "Content-Disposition": disposition,
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
        media_type=media,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Disposition": disposition,
        },
    )


def folder_lock(folder_id: str) -> asyncio.Lock:
    return _public_folder_locks[folder_id]
