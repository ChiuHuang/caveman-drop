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

The interface language follows your IP: Taiwan ranges
(1.32.208.0–1.32.215.255, 36.224.0.0–36.239.255.255, 120.120.0.0–120.123.255.255,
220.135.0.0–220.135.255.255) get Traditional Chinese, every other range gets
English. `?lang=zh-TW` / `?lang=en` switches it by hand.

Once signed in you get **My drive**, the way Google Drive works: upload a file,
click a folder to go into it, drag a file onto a folder row to move it, drag
files in from the desktop to upload them into that folder. The two icons in the
header are New folder and Upload, every row can be renamed, shared or deleted,
and folders and files sort together in one list. A second tab manages the
public side.

Source: <https://github.com/ChiuHuang/caveman-drop>

## Where to next

- **Quick start** — your first upload in 60 seconds.
- **API reference** — every endpoint, method and response shape.
- **Limits** — size caps and rate limits.
- **AI** — fetch `/llms.txt` or `/api` for the machine-readable version.
