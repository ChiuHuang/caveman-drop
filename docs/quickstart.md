# Quickstart

## Upload from curl

```bash
# New share folder + file in one call
curl -F file=@photo.jpg http://localhost:20042/api/public/upload
```

Response (JSON):

```json
{
  "success": true,
  "folder_id": "…",
  "file_id": "…",
  "download_url": "http://localhost:20042/dl/pub/…/…",
  "folder_url": "http://localhost:20042/f/…"
}
```

## Add to an existing folder

```bash
curl -F file=@notes.txt -F folder=FOLDER_ID http://localhost:20042/api/public/upload
```

## Upload from Python

```python
import httpx

with open("photo.jpg", "rb") as f:
    r = httpx.post("http://localhost:20042/api/public/upload", files={"file": f})
print(r.json()["download_url"])
```

## Upload from a browser

Open `/upload`, pick a file, and copy the link — or `POST` the same endpoint
with `fetch` + `FormData` (CORS is open).

## Private dashboard

Open `/login` and enter the server `PASSWORD` for chunked/resumable uploads,
the private file list (`/api/files`), and inline viewing (`/view/<id>`).
