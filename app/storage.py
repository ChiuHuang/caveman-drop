"""Filesystem storage helpers shared by all routes.

File ids are the sha256 of the file's bytes, so the same content always lands on
the same id and the same blob in the bin store (settings.bin_dir) — uploading it
twice costs one metadata entry, not a second copy. Folder ids stay UUIDs.
Payloads written before this scheme (UUID file ids) are still served, so old
links keep working.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import re
import shutil
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from .config import settings

PUBLIC_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
HASH_ID_RE = re.compile(r"^[0-9a-f]{64}$")
# Short share codes: the shortest unique prefix of the sha256, 6 chars unless a
# different file already starts with the same 6, then 7, and so on.
MIN_CODE = 6
MAX_CODE = 12
CODE_RE = re.compile(r"^[0-9a-f]{6,64}$")
_index_lock = threading.Lock()

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


def validate_file_id(value: str) -> None:
    """sha256 file id, or a legacy UUID id from before content addressing."""
    value = value or ""
    if not HASH_ID_RE.fullmatch(value) and not PUBLIC_ID_RE.fullmatch(value):
        raise HTTPException(400, "Invalid public file id")


# ---- content-addressed blob store (bin/) ----


def bin_path(file_id: str) -> str:
    """Where the bytes of `file_id` live. Two-level fanout keeps dirs small."""
    validate_file_id(file_id)
    if not HASH_ID_RE.fullmatch(file_id):
        raise HTTPException(400, "Not a content id")
    return os.path.join(settings.bin_dir, file_id[:2], file_id[2:4], file_id)


def payload_path(file_id: str, legacy_dir: str, ext: str = "") -> str:
    """Blob for a new-style id, or the old in-folder copy for a legacy UUID id."""
    if HASH_ID_RE.fullmatch(file_id or ""):
        return bin_path(file_id)
    validate_file_id(file_id)
    return os.path.join(legacy_dir, file_id + (ext or ""))


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def store_blob(src: str, known_hash: str | None = None) -> str:
    """Move `src` into the bin store under its sha256. Same bytes twice = one copy."""
    file_id = known_hash or file_sha256(src)
    target = bin_path(file_id)
    if os.path.exists(target):
        os.remove(src)  # already stored — don't keep a second copy
        return file_id
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        os.replace(src, target)
    except OSError:  # different filesystem (tmp mounted elsewhere)
        shutil.move(src, target)
    return file_id


def blob_referenced(file_id: str) -> bool:
    """True if any metadata entry still points at this blob."""
    if not HASH_ID_RE.fullmatch(file_id or ""):
        return False
    roots = (settings.public_dir, settings.single_dir, settings.upload_dir)
    for root in roots:
        for dirpath, _, names in os.walk(root):
            for fn in names:
                if fn != file_id + ".json":
                    continue
                try:
                    with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                        if json.load(f):
                            return True
                except (OSError, ValueError):
                    return True
    return False


def drop_blob(file_id: str) -> bool:
    """Delete a blob once nothing references it. True if bytes were removed."""
    if not HASH_ID_RE.fullmatch(file_id or "") or blob_referenced(file_id):
        return False
    try:
        os.remove(bin_path(file_id))
        return True
    except OSError:
        return False


def validate_upload_id(value: str) -> None:
    if not PUBLIC_ID_RE.fullmatch(value or ""):
        raise HTTPException(400, "Invalid upload id")


# ---- short share codes (catbox-style /usercontent/<code>.<ext>) ----


def _index_path() -> str:
    return os.path.join(settings.bin_dir, "short_index.json")


def _scan_public_hashes() -> dict[str, str]:
    """Every public sha256 on disk — the source of truth when the index is lost."""
    found: dict[str, str] = {}
    roots = [settings.single_dir] + [
        os.path.join(settings.public_dir, d) for d in _safe_listdir(settings.public_dir)
    ]
    for root in roots:
        for fn in _safe_listdir(root):
            if fn.endswith(".json") and HASH_ID_RE.fullmatch(fn[:-5]):
                found[fn[:-5]] = ""
    return found


def _safe_listdir(path: str) -> list[str]:
    try:
        return os.listdir(path)
    except OSError:
        return []


def _load_index() -> dict[str, dict[str, str]]:
    try:
        with open(_index_path(), encoding="utf-8") as f:
            data = json.load(f)
        codes = {str(k): str(v) for k, v in (data.get("codes") or {}).items()}
        hashes = {str(k): str(v) for k, v in (data.get("hashes") or {}).items()}
        if not codes and not hashes:
            raise ValueError
        return {"codes": codes, "hashes": hashes}
    except (OSError, ValueError, AttributeError):
        hashes = _scan_public_hashes()
        return {"codes": {}, "hashes": hashes}


def _save_index(idx: dict[str, dict[str, str]]) -> None:
    tmp = _index_path() + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(idx, f)
        os.replace(tmp, _index_path())
    except OSError:
        pass


def short_code(file_id: str) -> str:
    """Shortest unique prefix of this file's id, assigned on first use.

    Two different files that share their first 6 characters get 7, then 8 …
    whichever length is actually unique; past MAX_CODE the full id is used.
    """
    if not HASH_ID_RE.fullmatch(file_id or ""):
        return ""
    with _index_lock:
        idx = _load_index()
        code = idx["hashes"].get(file_id)
        if code:
            return code
        known = list(idx["hashes"])
        code = file_id
        for n in range(MIN_CODE, MAX_CODE + 1):
            cand = file_id[:n]
            if not any(h != file_id and h.startswith(cand) for h in known):
                code = cand
                break
        idx["hashes"][file_id] = code
        idx["codes"][code] = file_id
        _save_index(idx)
        return code


def resolve_short_code(code: str) -> str | None:
    """Public file_id behind a short code. Exact match only — no scanning, so
    random codes can't be used to burn CPU. The full 64-char id works too."""
    code = (code or "").strip().lower()
    if not CODE_RE.fullmatch(code):
        return None
    with _index_lock:
        hit = _load_index()["codes"].get(code)
    if hit:
        return hit
    return code if len(code) == 64 else None


def forget_short_code(file_id: str) -> None:
    with _index_lock:
        idx = _load_index()
        code = idx["hashes"].pop(file_id, None)
        if code and idx["codes"].get(code) == file_id:
            idx["codes"].pop(code, None)
            _save_index(idx)


def public_entry(dirname: str, file_id: str) -> dict[str, Any] | None:
    """Metadata for a public entry, only if its bytes are still there."""
    meta = entry_meta(dirname, file_id)
    if meta is None:
        return None
    if not os.path.exists(payload_path(file_id, dirname, meta.get("ext", ""))):
        return None
    return meta


def public_file_by_id(file_id: str) -> tuple[str, dict[str, Any]] | None:
    """(dirname, meta) for a public sha256, looking in singles then folders."""
    if not HASH_ID_RE.fullmatch(file_id or ""):
        return None
    meta = public_entry(settings.single_dir, file_id)
    if meta is not None:
        return settings.single_dir, meta
    for folder in _safe_listdir(settings.public_dir):
        d = os.path.join(settings.public_dir, folder)
        meta = public_entry(d, file_id)
        if meta is not None:
            return d, meta
    return None


def chunk_dir(prefix: str, upload_id: str) -> str:
    """Scratch dir for one chunked upload."""
    validate_upload_id(upload_id)
    if not re.fullmatch(r"[a-z]+", prefix or ""):
        raise HTTPException(400, "Invalid chunk prefix")
    d = os.path.join(settings.tmp_dir, f"{prefix}_{upload_id}")
    os.makedirs(d, exist_ok=True)
    return d


def assemble_chunks(
    chunk_dirname: str,
    total_chunks: int,
    max_bytes: int | None,
    staging: str | None = None,
) -> tuple[str, int]:
    """Concatenate part_0..N into the bin store keyed by sha256.

    Returns (file_id, bytes). `staging` holds the temporary copy (same volume as
    the bin store by default, so the final move is a rename). None = no cap.
    """
    limit = settings.max_chunked_parts
    if not 1 <= total_chunks <= limit:
        raise HTTPException(400, f"total_chunks must be 1..{limit}")
    staging = staging or settings.tmp_dir
    os.makedirs(staging, exist_ok=True)
    dest = os.path.join(staging, f"asm_{os.getpid()}_{int(time.time() * 1000) % 10_000_000}")
    digest = hashlib.sha256()
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
                        digest.update(c)
                        out.write(c)
        file_id = store_blob(dest, digest.hexdigest())
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
    return file_id, written


def public_folder_dir(folder_id: str) -> str:
    validate_public_id(folder_id, "folder id")
    return os.path.join(settings.public_dir, folder_id)


def save_entry(dirname: str, file_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Write the metadata sidecar for one file entry."""
    meta = {"ctime": time.time(), **meta}
    with open(os.path.join(dirname, file_id + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return meta


def entry_meta(dirname: str, file_id: str) -> dict[str, Any] | None:
    """Metadata for one file entry, plus its payload size, or None if it is gone."""
    if not (HASH_ID_RE.fullmatch(file_id or "") or PUBLIC_ID_RE.fullmatch(file_id or "")):
        return None  # e.g. folder.json — not a file entry
    jp = os.path.join(dirname, file_id + ".json")
    if not os.path.exists(jp):
        return None
    try:
        with open(jp, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    meta.setdefault("filename", file_id)
    try:
        path = payload_path(file_id, dirname, meta.get("ext", ""))
        meta["size"] = int(meta.get("size") or os.path.getsize(path))
        meta["ctime"] = meta.get("ctime") or os.path.getctime(path)
    except OSError:
        return None
    return meta


def public_folder_files(folder_id: str) -> list[dict[str, Any]]:
    d = public_folder_dir(folder_id)
    out: list[dict[str, Any]] = []
    if not os.path.isdir(d):
        return out
    for fn in os.listdir(d):
        if not fn.endswith(".json") or fn == "folder.json":
            continue
        fid = fn[:-5]
        meta = entry_meta(d, fid)
        if meta is None:
            continue
        out.append(
            {
                "id": fid,
                "name": meta["filename"],
                "description": meta.get("description", ""),
                "ext": meta.get("ext", ""),
                "size": meta["size"],
                "ctime": meta["ctime"],
                "content_type": meta.get(
                    "content_type",
                    mimetypes.guess_type(meta.get("filename", ""))[0]
                    or "application/octet-stream",
                ),
            }
        )
    out.sort(key=lambda x: x["ctime"], reverse=True)
    return out


def private_files() -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    folders = get_private_folders()
    if not os.path.isdir(settings.upload_dir):
        return files
    for fn in os.listdir(settings.upload_dir):
        if not fn.endswith(".json") or fn in ("folders.json", "shares.json"):
            continue
        fid = fn[:-5]
        meta = entry_meta(settings.upload_dir, fid)
        if meta is None:
            continue
        size = meta["size"]
        fid_folder = meta.get("folder")
        files.append(
            {
                "id": fid,
                "name": meta["filename"],
                "description": meta.get("description", ""),
                "size": size // 1024,
                "bytes": size,
                "ctime": meta["ctime"],
                "folder": fid_folder,
                "folder_name": (folders.get(fid_folder) or {}).get("name", "") if fid_folder else "",
            }
        )
    files.sort(key=lambda x: x["ctime"], reverse=True)
    return files


def stream_download(
    request: Request,
    path: str,
    fname: str,
    inline: bool = False,
    content_type: str | None = None,
    cache: bool = False,
) -> StreamingResponse:
    """Range-aware download. `inline=True` renders in-browser (preview).

    `cache=True` marks the response immutable (content-addressed URLs), so a CDN
    in front of the server can hold it for a year.
    """
    if not os.path.exists(path):
        raise HTTPException(404)
    file_size = os.path.getsize(path)
    media = content_type or "application/octet-stream"
    disposition = ("inline" if inline else "attachment") + f'; filename="{fname}"'
    rng = request.headers.get("range")
    immutable = {"Cache-Control": "public, max-age=31536000, immutable"} if cache else {}

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
                **immutable,
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
            **immutable,
        },
    )


def folder_lock(folder_id: str) -> asyncio.Lock:
    return _public_folder_locks[folder_id]


def single_meta(file_id: str) -> dict[str, Any]:
    meta = entry_meta(settings.single_dir, file_id)
    if meta is None:
        raise HTTPException(404, "File not found")
    return meta


def single_blob(file_id: str, ext: str = "") -> str:
    """Payload of a folderless public file (bin store, or legacy copy)."""
    return payload_path(file_id, settings.single_dir, ext)


def delete_file_entry(dirname: str, file_id: str) -> bool:
    """Remove one metadata entry, and its blob when nothing else points at it."""
    ext = ""
    try:
        with open(os.path.join(dirname, file_id + ".json"), encoding="utf-8") as f:
            ext = str(json.load(f).get("ext", "") or "")
    except (OSError, ValueError):
        pass
    removed = False
    try:
        os.remove(os.path.join(dirname, file_id + ".json"))
        removed = True
    except OSError:
        pass
    if not HASH_ID_RE.fullmatch(file_id or ""):
        try:  # legacy copy stored next to the metadata
            os.remove(os.path.join(dirname, file_id + ext))
        except OSError:
            pass
    drop_blob(file_id)
    return removed


def _private_folders_path() -> str:
    return os.path.join(settings.upload_dir, "folders.json")


def get_private_folders() -> dict[str, dict]:
    try:
        with open(_private_folders_path(), encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_private_folders(d: dict) -> None:
    with open(_private_folders_path(), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def create_private_folder(name: str) -> tuple[str, dict]:
    import uuid

    fid = str(uuid.uuid4())
    meta = {"name": (name or "").strip()[:64] or "未命名資料夾", "ctime": time.time()}
    d = get_private_folders()
    d[fid] = meta
    save_private_folders(d)
    return fid, meta


def delete_private_folder(fid: str) -> int:
    d = get_private_folders()
    if fid not in d:
        raise HTTPException(404, "Folder not found")
    n = 0
    for fn in os.listdir(settings.upload_dir):
        if not fn.endswith(".json") or fn in ("folders.json", "shares.json"):
            continue
        jp = os.path.join(settings.upload_dir, fn)
        try:
            with open(jp, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if meta.get("folder") == fid:
            if delete_file_entry(settings.upload_dir, fn[:-5]):
                n += 1
    d.pop(fid, None)
    save_private_folders(d)
    shares = get_shares()
    for token in [t for t, s in shares.items() if s.get("folder_id") == fid]:
        shares.pop(token, None)
    save_shares(shares)
    return n


def public_folder_name(folder_id: str) -> str:
    try:
        with open(os.path.join(public_folder_dir(folder_id), "folder.json"), encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("name", "") or "")
    except (OSError, ValueError):
        return ""


def clean_name(name: str, limit: int = 64) -> str:
    """Free-text display name: control characters out, length capped."""
    return re.sub(r"[\x00-\x1f\x7f]", "", str(name or "")).strip()[:limit]


def create_public_folder(name: str) -> tuple[str, dict[str, Any]]:
    """Create an empty public folder under a free-text name."""
    import uuid

    fid = str(uuid.uuid4())
    fdir = public_folder_dir(fid)
    os.makedirs(fdir, exist_ok=True)
    meta = {"name": clean_name(name) or "未命名資料夾", "ctime": time.time()}
    with open(os.path.join(fdir, "folder.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return fid, meta


def resolve_public_folder(ref: str) -> str:
    """A folder_id is used as-is; any other text becomes a new folder's name."""
    ref = str(ref or "").strip()
    if not ref:
        raise HTTPException(400, "Missing folder")
    if PUBLIC_ID_RE.fullmatch(ref):
        return ref
    return create_public_folder(ref)[0]


def _shares_path() -> str:
    return os.path.join(settings.upload_dir, "shares.json")


def get_shares() -> dict[str, dict]:
    try:
        with open(_shares_path(), encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_shares(d: dict) -> None:
    with open(_shares_path(), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def create_share(folder_id: str, mode: str) -> tuple[str, dict]:
    import uuid

    if mode not in ("view", "upload"):
        raise HTTPException(400, "mode must be view or upload")
    if folder_id not in get_private_folders():
        raise HTTPException(404, "Folder not found")
    token = str(uuid.uuid4())
    meta = {"folder_id": folder_id, "mode": mode, "ctime": time.time()}
    d = get_shares()
    d[token] = meta
    save_shares(d)
    return token, meta


def get_share(token: str) -> dict | None:
    return get_shares().get(token)


def revoke_share(token: str) -> bool:
    d = get_shares()
    if token not in d:
        return False
    d.pop(token, None)
    save_shares(d)
    return True


_ip_tags: dict[str, tuple[int, float]] = {}
_probe_log: dict[str, deque] = defaultdict(deque)


def threads_for_speed(bps: float) -> int:
    MB = 1024 * 1024
    if bps > 10 * MB:
        return 16
    if bps > 5 * MB:
        return 32
    if bps > 2 * MB:
        return 64
    return 128


def speed_probe(nbytes: int, request: Request, client_ms: str | None = None) -> tuple[int, float]:
    """Link speed + recommended thread count.

    The browser's own timing wins when present: it covers DNS/TCP/TLS and the
    full round trip, which a server-side timer (started only once the request
    reached the app) cannot see. Falls back to the server-side elapsed time.
    """
    server_s = max(time.time() - getattr(request.state, "t0", time.time()), 0.001)
    elapsed = server_s
    try:
        client_s = float(client_ms or 0) / 1000.0
    except (TypeError, ValueError):
        client_s = 0.0
    if 0.002 <= client_s <= 60:
        elapsed = client_s
    bps = nbytes / elapsed
    return threads_for_speed(bps), bps


def probe_check(ip: str) -> None:
    dq = _probe_log[ip]
    now = time.time()
    _prune(dq, now)
    if len(dq) >= 20:
        raise HTTPException(429, "Too many probes")
    dq.append((now, 0))


def tag_ip(ip: str, threads: int) -> None:
    _ip_tags[ip] = (threads, time.time())


def tagged_threads(ip: str) -> int | None:
    tag = _ip_tags.get(ip)
    if not tag:
        return None
    threads, ts = tag
    if time.time() - ts > _bw_window():
        _ip_tags.pop(ip, None)
        return None
    return threads


def sweep_tmp() -> int:
    import shutil

    ttl = settings.tmp_max_age_hours * 3600
    now = time.time()
    removed = 0
    try:
        entries = list(os.scandir(settings.tmp_dir))
    except OSError:
        return 0
    for entry in entries:
        try:
            latest = entry.stat().st_mtime
            if entry.is_dir(follow_symlinks=False):
                for root, _, files in os.walk(entry.path):
                    for fn in files:
                        try:
                            mt = os.path.getmtime(os.path.join(root, fn))
                            if mt > latest:
                                latest = mt
                        except OSError:
                            pass
            if now - latest < ttl:
                continue
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path, ignore_errors=True)
            else:
                os.remove(entry.path)
            removed += 1
        except OSError:
            continue
    return removed
