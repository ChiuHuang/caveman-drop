# CaveMan Drop

Anonymous file sharing, text-first. People get a Material Design interface;
scripts and AI get plain JSON / plain text.

## How it works

1. **Upload** a file — no account needed:
   `POST /api/public/upload`, multipart field named `file`.
2. Get back a **download link** (`/dl/pub/…`) and a **folder link** (`/f/…`).
3. Share the folder link. Anyone with it can download, and can add more files
   to the same folder with the same endpoint.

Browsers get the MDUI web interface; `curl`, Python and AI agents get JSON or
plain text. `?format=html` / `?format=json` forces one.

The interface language is decided by the **browser**: a small inline script
in every page reads `navigator.languages` (Traditional-reading zh-TW / Hant /
HK / MO browsers get Traditional Chinese, everything else gets English),
stores the pick in a `lang` cookie and reloads once when needed.
`?lang=zh-TW` / `?lang=en` switches it by hand.

Once signed in you get **My drive**, the way Google Drive works: upload a file,
click a folder to go into it, drag a file onto a folder row to move it, drag
files in from the desktop to upload them into that folder. The two icons beside
the title are New folder and Upload, every row can be renamed, shared or
deleted, and folders and files sort together in one list. A second tab manages
the public side.

A private-only host (`PRIVATE_ONLY_HOSTS`, `pvf.chiuhuang.dev` by default) drops
all of that chrome: `/` is the login page when you are signed out and the drive
on its own — no tabs, no public UI — when you are signed in.

Source: <https://github.com/ChiuHuang/caveman-drop>

## Where to next

- **Quick start** — your first upload in 60 seconds.
- **API reference** — every endpoint, method and response shape.
- **Limits** — size caps and rate limits.
- **Self-hosting** — install, `.env` settings and the reverse proxy.
- **AI** — fetch `/llms.txt` or `/api` for the machine-readable version.
