# CaveMan Drop

Anonymous, text-first file sharing. Upload a file from any script, browser, or
AI agent — get a permanent link back. No account required for public shares.

- **Browsers** get a Material Design 3 UI (MDUI v2) on every page and endpoint.
- **Scripts and agents** (`curl`, Python, AI tools) get plain JSON / text via
  content negotiation. Append `?format=json` or `?format=html` to force either.
- Machine-readable docs live at `/llms.txt`; the full API index at `/api`.

## Quick start

```bash
# 1. Configure
cp .env.example .env   # then set PASSWORD

# 2. Install + run (uv is fastest on Windows)
uv venv
# PowerShell: .venv\Scripts\Activate.ps1
uv pip install fastapi "uvicorn[standard]" python-dotenv python-multipart itsdangerous markdown httpx
uv run main.py
# or: uv run uvicorn main:app --host 0.0.0.0 --port 20042
```

Upload your first file:

```bash
curl -F file=@photo.jpg http://localhost:20042/api/public/upload
```

## Layout

```
main.py              # entry point (uvicorn)
app/
  __init__.py        # FastAPI factory, middleware, error pages
  config.py          # .env settings (ports, secrets, limits, dirs)
  negotiation.py     # browser-vs-agent content negotiation
  storage.py         # file storage, quotas, rate limits, downloads
  ui.py              # MDUI v2 HTML shell shared by every page
  static/            # app.css + app.js (served at /static)
  routes/
    pages.py         # /, /login, /logout, /upload, /f/{folder}
    public_api.py    # POST /api/public/upload|folder, GET folder/file, /dl/pub/…
    private_api.py   # password + mobile-token routes, chunk upload, /dl, /view, /del
    system.py        # /api index, /llms.txt
    docs.py          # GitBook-style /docs served from docs/*.md
docs/                # Markdown source for /docs (also readable on GitHub)
```

## Configuration

See `.env.example`. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `PORT` (`SERVER_PORT` also works) | `20042` | Listen port |
| `PASSWORD` | `passw` | Private dashboard password — **change this** |
| `SECRET_KEY` | auto-generated | Session signing (persisted to `.secret_key`) |
| `UPLOAD_DIR` / `TMP_DIR` / `PUBLIC_DIR` | `airdrop_files` / `airdrop_tmp` / `public_uploads` | Storage |
| `MAX_FILE_SIZE_GB` | `5` | Per-file cap |
| `MAX_MULTI_FOLDER_TOTAL_GB` | `1` | Combined cap once a folder holds >1 file |
| `RATE_LIMIT_MAX_UPLOADS` / `RATE_LIMIT_WINDOW_SECONDS` | `30` / `3600` | Per-IP upload throttle |

## Docs

- In-app guides: `/docs`, `/docs/quickstart`, `/docs/api`, `/docs/limits`
- Agent docs: `/llms.txt`
- Same content as Markdown in `docs/` for GitHub browsing.
