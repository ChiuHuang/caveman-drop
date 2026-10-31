# Self-hosting

CaveMan Drop is a plain FastAPI application: give it a Python (3.11+), a
directory for the files and a `.env`, and it runs. This page covers setup,
configuration, auto-updating on boot and sitting behind a reverse proxy.

## Install and run

```bash
git clone https://github.com/ChiuHuang/caveman-drop
cd caveman-drop

cp .env.example .env    # change PASSWORD at the very least

uv venv
uv pip install -r requirements.txt
uv run main.py
# or: uv run uvicorn main:app --host 0.0.0.0 --port 20042
# or (production): .venv/bin/python -m gunicorn app:app -w 1 \
#   -k uvicorn.workers.UvicornWorker -b 0.0.0.0:20042
```

`requirements.txt` already includes gunicorn, which suits a systemd service.

## Boot / auto-update: `deploy.sh`

`deploy.sh` is POSIX sh — point systemd, pelican/pterodactyl or cron at it:

1. The first run does `git init` and aligns with `origin/main`; later runs
   `git pull --ff-only` to auto-update (when `AUTO_UPDATE=1`).
2. Creates `.venv` if missing; creates `.env` from `.env.example` if missing.
3. Re-runs `pip install` only when the sha256 of `requirements.txt` changes.
4. Finally starts gunicorn listening on `0.0.0.0:20042`.

Example unit (adjust `WorkingDirectory`):

```ini
[Unit]
Description=CaveMan Drop
After=network.target

[Service]
WorkingDirectory=/srv/caveman-drop
ExecStart=/bin/sh ./deploy.sh
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

## Configuration (.env)

| Variable | Default | Purpose |
|---|---|---|
| `PORT` (`SERVER_PORT` also works) / `HOST` | `20042` / `0.0.0.0` | Listen address |
| `PASSWORD` | `passw` | Private mode password — **change it** |
| `SECRET_KEY` | auto-generated | Session signing (persisted to `.secret_key`) |
| `PUBLIC_BASE_URL` | empty | Fixed base for generated links; empty = follow the request |
| `PRIVATE_ONLY_HOSTS` | `pvf.chiuhuang.dev` | Hosts that serve the private drive only (comma separated) |
| `UPLOAD_DIR` / `TMP_DIR` / `PUBLIC_DIR` / `SINGLE_DIR` | `airdrop_files` / `airdrop_tmp` / `public_uploads` / `public_singles` | Storage locations |
| `BIN_DIR` | `bin` | sha256 blob store (one copy per content) |
| `MAX_FILE_SIZE_GB` / `MAX_CHUNKED_PARTS` | `5` / `16384` | Public per-file limit / chunk count limit |
| `TMP_MAX_AGE_HOURS` | `24` | When abandoned chunk dirs are swept |
| `RATE_LIMIT_WINDOW_SECONDS` / `RATE_LIMIT_MAX_UPLOADS` | `3600` / `30` | Per-IP upload rate limit |
| `BW_WINDOW_SECONDS` | `600` | Bandwidth accounting window (seconds) |
| `BW_IP_SOFT_MB` | `100` | Per-IP traffic per window before throttling |
| `BW_FOLDER_HARD_GB` | `5` | Per-folder per-window cap |
| `BW_FOLDERS_PER_WINDOW` | `10` | Distinct folders per IP per window |
| `THROTTLE_MAX_MBPS` / `THROTTLE_MIN_MBPS` | `90` / `40` | Throttle start and floor |
| `BW_TIER_GB` / `BW_TIER_MBPS` | `1` / `10` | Minus 10 Mbps per extra GB |

## Reverse proxy and link direction

- The client IP comes from `CF-Connecting-IP` → `X-Forwarded-For` → the
  connection address, so rate limiting stays correct behind Cloudflare.
  Signed-in sessions are never rate limited.
- Generated links come from `app/urls.py`: HTTPS in → HTTPS out (reads
  `Forwarded` / `X-Forwarded-Proto` / `X-Forwarded-Host`). If the proxy sends
  no headers, set `PUBLIC_BASE_URL` to pin the domain.
- Those headers are trusted: firewall the backend port against direct access,
  or simply set `PUBLIC_BASE_URL`.
- The `/usercontent/<code>.<ext>` short path carries
  `Cache-Control: immutable`, so it can be pointed at the same machine and
  handed to a CDN as-is.

## Storage and cleanup

- `file_id` is the sha256 of the content: bytes live once in `BIN_DIR`
  (`bin/` by default) and re-uploads reuse them. The blob is deleted only
  when its last reference goes away.
- Chunked-upload parts land in `TMP_DIR`; abandoned dirs older than
  `TMP_MAX_AGE_HOURS` (24 by default) are swept by a background task.
- Single public files (no folder) go to `SINGLE_DIR`; public files with
  folders and their listing to `PUBLIC_DIR`; private files to `UPLOAD_DIR`.

## Interface language

The **browser** decides the language: an inline script in every page's
`<head>` reads `navigator.languages` (zh-TW/Hant/HK/MO → Traditional Chinese,
everything else → English), stores the pick in a `lang` cookie and reloads
once when needed. `?lang=zh-TW` / `?lang=en` overrides it. JSON, plain text
and `/llms.txt` are always English, so scripts never care.
