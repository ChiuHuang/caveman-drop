# API reference

Base URL: the server root, e.g. `http://localhost:20042`.

Content negotiation: send a browser `User-Agent` + `Accept: text/html` to get
the MDUI HTML console; anything else gets JSON/text. `?format=json|html|text`
forces one representation.

## Public (no auth)

### `POST /api/public/upload`

Anonymous upload. Multipart fields: `file` (required), `folder` (optional
existing folder id). Returns `folder_id`, `file_id`, `filename`,
`size_bytes`, `content_type`, `url`, `download_url`, `folder_url`,
`share_url`, `folder_api_url`, `file_api_url`.

### `POST /api/public/folder`

Create an empty folder. Returns `folder_id`, `folder_url`, `upload_url`,
`folder_api_url`.

### `GET /api/public/folder/{folder_id}`

Folder metadata + `files[]` with per-file `download_url` / `file_api_url`.
Browsers see the folder UI instead.

### `GET /api/public/file/{folder_id}/{file_id}`

One file's metadata: `filename`, `size_bytes`, `content_type`,
`download_url`. Browsers see a file detail card.

### `GET /dl/pub/{folder_id}/{file_id}`

Download bytes. Supports `Range:` requests for resume/parallel fetch.

## Private (password session or `?token=` mobile token)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/files` | Private file list (JSON, or HTML for browsers) |
| `POST` | `/api/upload_chunk` | Fields: `file_chunk`, `upload_id`, `index`, `filename` |
| `POST` | `/api/merge_chunks` | JSON: `upload_id`, `filename`, `total_chunks` |
| `GET` | `/dl/{file_id}` | Range-aware private download |
| `GET` | `/view/{file_id}` | Inline view |
| `GET` | `/del/{file_id}` | Delete (browsers redirect home) |
| `GET/POST` | `/m/{token}` | Single-file mobile upload (iPhone Shortcuts compatible) |
| `GET/POST` | `/login`, `GET /logout` | Password session |

## System

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api` | Full JSON index of the API (HTML console for browsers) |
| `GET` | `/llms.txt`, `/api/llms.txt` | Agent-oriented docs, always plain text |
| `GET` | `/docs`, `/docs/{page}` | GitBook-style guides (Markdown for agents) |
