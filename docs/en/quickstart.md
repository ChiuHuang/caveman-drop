# Quick start

## Upload one file (no folder)

```bash
curl -F file=@photo.jpg http://localhost:20042/api/public/upload
```

Response (JSON): a direct download link, no folder created. `file_id` is the
sha256 of the content.

```json
{
  "success": true,
  "file_id": "…64 hex chars, sha256…",
  "deduplicated": false,
  "short_url": "https://usercontent.qiuhuang.dev/usercontent/f127ca.jpg",
  "download_url": "http://localhost:20042/dl/s/…"
}
```

Upload the same file again and `file_id`, `short_url` and `download_url` come
back identical, with `deduplicated: true` — the server keeps one copy of the
bytes (`bin/`), never two.

`short_url` is the CDN-friendly short link: the shortest unique prefix of the
sha256 (6 characters, longer on a clash), served with an `immutable` cache
header. You can attach a free-text description too:

```bash
curl -F file=@photo.jpg -F 'description=Penghu trip 2026' http://localhost:20042/api/public/upload
```

## Folders, and uploading several files into one

Create a folder in the web UI (or with the API below), share its link, and
anyone uploading on that folder page adds to the same bundle. From a script:

```bash
curl -X POST http://localhost:20042/api/public/folder -H 'Content-Type: application/json' -d '{"name":"Album"}'
curl -F file=@notes.txt -F folder=FOLDER_ID http://localhost:20042/api/public/upload
```

`folder` is deliberately forgiving: an id adds the file to that folder, and any
other text creates a new folder with that name and uploads into it. The folder
field in the web form follows the same rule (leave it empty for a single direct
file).

## HTTPS links

Returned links follow the request: an HTTPS request gets HTTPS URLs back
(`Forwarded` / `X-Forwarded-Proto` are honoured). If your reverse proxy sends
neither, set `PUBLIC_BASE_URL=https://file.example.com` to pin the domain.

## Upload from Python

```python
import httpx

with open("photo.jpg", "rb") as f:
    r = httpx.post("http://localhost:20042/api/public/upload", files={"file": f})
print(r.json()["download_url"])
```

## Upload from a browser

Open `/upload` and pick a file: it uploads in chunks with a live monitor below
— total progress, speed (measured from real elapsed time, plus the overall
average), a segment bar and per-thread state, and a pause button. When it
finishes you get the download link, the folder link and the average speed.

## Big files: chunked upload from a script

```python
import httpx, uuid, math

BASE = "http://localhost:20042"
uid = str(uuid.uuid4())
data = open("big.bin", "rb").read()
CS, total = 4 * 1024 * 1024, math.ceil(len(data) / (4 * 1024 * 1024))
for i in range(total):
    httpx.post(f"{BASE}/api/public/chunk", files={"file_chunk": data[i*CS:(i+1)*CS]},
               data={"upload_id": uid, "index": str(i), "filename": "big.bin"})
r = httpx.post(f"{BASE}/api/public/merge_chunks",
               json={"upload_id": uid, "filename": "big.bin", "total_chunks": total})
print(r.json()["download_url"])
```

The browser fires no separate probe: it starts with 16 threads and decides how
many to add from the **real throughput of the first few chunks** (32 / 64 / 128
on a slow link, 16 on a fast one). The number comes from XHR's upload progress
events, so it is bytes actually sent per second — not latency — and no probe
traffic is wasted. `/api/public/probe` is still there for curl, scripts and AI
that want to measure a link themselves.

## Private mode

Open `/login` and enter the server `PASSWORD`: chunked upload, the private file
list (`/api/files`), inline preview (`/view/<id>`), download and delete, plus
the drive with folders. Signed in, the interface shows only the private space
and the shared-bandwidth throttle does not apply.
