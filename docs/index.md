# CaveMan Drop

Anonymous, text-first file sharing with a Material Design UI for humans and a
plain JSON/text API for scripts and AI agents.

## How it works

1. **Upload** a file — no account needed:
   `POST /api/public/upload` with a multipart field named `file`.
2. You get back a **download URL** (`/dl/pub/…`) and a **folder URL** (`/f/…`).
3. Share the folder URL. Anyone with it can download — or add more files with
   the same endpoint plus a `folder` field.

Browsers automatically see an MDUI web UI; `curl`, Python, and AI agents see
JSON or plain text. Use `?format=html` / `?format=json` to override.

## Where to go next

- **Quickstart** — your first upload in 60 seconds.
- **API reference** — every endpoint, method, and payload.
- **Limits & fair use** — size caps and rate limits.
- **Agents** — fetch `/llms.txt` or `/api` for machine-readable docs.
