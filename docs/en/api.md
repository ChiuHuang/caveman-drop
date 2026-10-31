# API reference

Base URL: the root of the server, e.g. `http://localhost:20042`.

Links always follow the request: an HTTPS request gets HTTPS URLs back
(`Forwarded` / `X-Forwarded-Proto` are honoured). Set `PUBLIC_BASE_URL` to pin
the domain.

`file_id` **is the sha256 of the file's content**: the same id means
byte-identical content. The bytes are stored once (`BIN_DIR`, `bin/` by
default), so re-uploading costs no extra space and returns the same link.
Responses carry `deduplicated: true` when those bytes were already stored.

## Short links (for a CDN)

`GET /{code}.{ext}` — `code` is the **shortest unique prefix** of
the sha256: usually 6 characters (catbox style), automatically 7, 8 … if
another file starts with the same characters. Responses carry
`Cache-Control: public, max-age=31536000, immutable`, so the link never expires
and a Cloudflare cache can hold it. Every upload and listing response includes
`short_url`.

Only public files resolve here; private uploads never appear on this path, so
the short codes cannot be used to probe for them.

```json
{
  "file_id": "f127ca62682b836ac65639814a83d44ce2ff4008209605cb39e444afd6fa2923",
  "short_url": "https://usercontent.qiuhuang.dev/f127ca.pdf",
  "download_url": "https://file.chiuhuang.dev/dl/s/f127ca…"
}
```

Content negotiation: a browser `User-Agent` with `Accept: text/html` gets the
MDUI HTML console, everything else gets JSON / plain text.
`?format=json|html|text` forces one.

## Public (no auth)

### `POST /api/public/upload`

Anonymous upload. Multipart fields: `file` (required), `folder` (optional),
`description` (optional). An existing `folder` id adds the file there; any
other text creates a new folder with that name. Without `folder` it is a
single direct file and no folder is created. Returns `file_id`, `filename`,
`description`, `size_bytes`, `short_url`, `download_url`, `file_api_url`; the
`folder_url` family only comes back when a folder was used.

```bash
curl -F file=@photo.jpg http://localhost:20042/api/public/upload
curl -F file=@photo.jpg -F folder=Album http://localhost:20042/api/public/upload
curl -F file=@photo.jpg -F 'description=Penghu trip 2026' http://localhost:20042/api/public/upload
```

### `POST /api/public/chunk` → `POST /api/public/merge_chunks`

Chunked upload (browsers use it automatically). POST the parts in parallel
(multipart: `file_chunk`, `upload_id`, `index`, `filename`), then POST JSON
(`upload_id`, `filename`, `total_chunks`, optional `folder` (id or name),
optional `description`) to merge. The response matches the single-POST upload.

### `POST /api/public/folder/rename` (admin)

```bash
curl -X POST https://this.host/api/public/folder/rename \
     -H "Content-Type: application/json" \
     -d '{"folder_id":"FOLDER_UUID","name":"new name"}'
```

Only the display name changes. The `folder_id`, the share URL and every file
link inside keep working.

### `POST /api/public/folder`

Create an empty folder (optional JSON `name`, and `perm` for what non-owners
may do: `readonly` = list + download, `upload` = dropbox, `both` = the default,
everything open). Created from a browser, the folder is **assigned to that
session**: its creator can rename it (`/api/public/folder/rename`), change the
permission (`/api/public/folder/perm`), or delete it (`/delpubdir/{folder_id}`)
without signing in. Returns `folder_id`, `folder_name`, `folder_url`,
`upload_url`, `folder_api_url`.

### `GET /api/public/folder/{folder_id}`

Folder metadata plus `files[]`, each with `name`, `description`,
`download_url`, `short_url`, `file_api_url`. Browsers get the folder UI.

### `GET /api/public/file/{folder_id}/{file_id}`

One file's metadata: `filename`, `description`, `size_bytes`, `content_type`,
`short_url`, `download_url`. Browsers get a file card with a preview.

### `GET /dl/pub/{folder_id}/{file_id}`

The bytes. Supports `Range:` for resume and parallel fetching. Add
`?preview=1` to serve it inline for browser preview.

### Single direct files (no folder)

- `GET /api/public/single/{file_id}` — metadata and direct link.
- `GET /dl/s/{file_id}` — download (`?preview=1` to preview).

### `POST /api/public/upload_url` (upload from a URL)

JSON `{"url", "folder" (optional), "description" (optional)}`: the server
fetches the URL through `PROXY_BASE_URL` (default
`https://proxy.chiuhuang.dev`) and stores the bytes exactly like an ordinary
public upload (same `folder` rules as above). Anonymous calls are throttled to
`URL_THROTTLE_MBPS` (60 by default); a signed-in session is uncapped. The
response has the same shape as `/api/public/upload`.

### Download a whole folder as .zip

- `GET /zip/f/{folder_id}` — a public folder as one `.zip`, named after the folder.
- `GET /zip/{folder_id}` — a private folder; needs a signed-in session.

The zip is **streamed live**: built in memory step by step, never written to
disk. Flat (no subdirectories); duplicate names get a ` (1)`-style suffix.
The public zip follows the folder's `perm`: an upload-only folder zips with a
403.

### Private folders as share links (`/s/{token}`)

- `POST /api/folders/{folder_id}/share` — body `{"mode": "view" | "upload" |
  "both"}` (omit it to use the folder's `perm`). Returns the `/s/{token}` URL.
- `view` = list + download; `upload` = anonymous dropbox (contents stay
  hidden); `both` = everything. `POST /api/folders` takes a `perm` to set the
  default, and `POST /api/folders/perm` changes it.

## Clients behind a proxy: `?auth=`

A CORS-style proxy (`https://proxy.example/https://this.host/...`) forwards
the request but never hands our `Set-Cookie` back to the browser, so a cookie
session cannot work on that path. When you have to go that way, put
`?auth=<PASSWORD>` on **every** request:

```bash
curl "https://proxy.example/https://this.host/api/files?auth=YOUR_PASSWORD"
curl -F file=@big.iso "https://proxy.example/https://this.host/api/upload_chunk?auth=YOUR_PASSWORD" \
     -F upload_id=... -F index=0 -F filename=big.iso
```

- Honoured over **HTTPS** only (plain HTTP is refused).
- The password is never written back into a response or a redirect;
  `/login?auth=…` sets the cookie and 303s to `/` with the parameter dropped.
- 10 wrong guesses from one IP lock it out for 10 minutes (`429`).
- The password ends up in the address bar and in proxy logs, so only use this
  in a trusted environment.

## Private (password session, `?auth=`, or the `?token=` mobile token)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/files` | Private file list (JSON; browsers get HTML) |
| `POST` | `/api/upload_chunk` | Fields: `file_chunk`, `upload_id`, `index`, `filename` |
| `POST` | `/api/merge_chunks` | JSON: `upload_id`, `filename`, `total_chunks`, optional `folder_id` |
| `POST` | `/api/folders` | JSON `name`, optional `perm` (view / upload / both) — new folder in the drive |
| `POST` | `/api/folders/rename` | JSON `folder_id`, `name` — rename; id, files and share links stay |
| `POST` | `/api/folders/perm` | JSON `folder_id`, `perm` (`view` / `upload` / `both`) — default share-link mode |
| `GET` | `/api/folders` | Folder list with file counts |
| `GET`/`POST` | `/deldir/{folder_id}` | Delete a private folder and its files |
| `GET` | `/?folder={folder_id}` | The drive view: rows, breadcrumb, drop targets |
| `POST` | `/api/folders/{id}/share` | JSON `mode` (`view` / `upload` / `both`, default = the folder's perm) — a no-login share link |
| `POST` | `/api/share/revoke` | JSON `token` — revoke a share |
| `GET` | `/s/{token}` | Shared folder page (browser UI / plain text) |
| `POST` | `/api/share/merge_chunks` | JSON `upload_id`, `filename`, `total_chunks`, `token` — upload via a share link |
| `GET` | `/dl/sh/{token}/{file_id}` | Share download (`?preview=1` to preview) |
| `GET` | `/dl/{file_id}` | Range-capable private download (`?preview=1` to preview) |
| `GET` | `/view/{file_id}` | Inline preview |
| `GET`/`POST` | `/del/{file_id}` | Delete (`POST` keeps the page on the folder it is showing) |
| `POST` | `/api/files/rename` | JSON `file_id`, `name` — rename a file; id and bytes stay |
| `POST` | `/api/files/move` | JSON `file_id`, `folder_id`, `from_folder_id` — drag and drop move |
| `POST` | `/api/public/file/rename` | Same, for a public file; add `folder_id` |
| `POST` | `/api/public/folder/rename` | JSON `folder_id`, `name` — rename a public folder; the URL stays. Also the creating session's right |
| `POST` | `/api/public/folder/perm` | JSON `folder_id`, `perm` (`readonly` / `upload` / `both`) — what non-owners may do |
| `POST` | `/api/public/move` | Same body as the private move |
| `POST` | `/delpub/{file_id}`, `/delpubdir/{folder_id}` | Remove from every public folder (admin or the owner session) |
| `GET/POST` | `/m/{token}` | Single-file phone upload (iPhone Shortcuts compatible) |
| `GET/POST` | `/login`, `GET /logout` | Password session |

## System

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api` | Full JSON index (browsers get the HTML console) |
| `GET` | `/llms.txt`, `/api/llms.txt` | The AI-facing document, always plain text |
| `GET` | `/docs`, `/docs/{page}` | The guide (agents get the Markdown source) |
