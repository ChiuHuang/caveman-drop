"""Human page routes: /, /login, /logout, /upload, /f/{folder_id}.

Browsers get the MDUI UI (Traditional Chinese); scripts/agents keep the
original plain-text output. After login the site switches to private mode —
no public upload affordances are shown.
"""

from __future__ import annotations

import html

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from ..config import settings
from ..negotiation import wants_html
from ..storage import private_files, public_folder_files
from ..ui import endpoint_card, file_rows, page, private_panel

router = APIRouter()


def _dashboard_html(request: Request, authed: bool) -> str:
    base = str(request.base_url).rstrip("/")
    if authed:
        files = private_files()
        return page(
            "私人模式",
            f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>私人模式</h1>
          <p>已登入 — 這裡只有你的私人檔案，不會顯示公開上傳。</p>
          <div class="form-row">
            <a href="/api/files"><mdui-button variant="outlined">檔案 API</mdui-button></a>
            <a href="/logout"><mdui-button variant="text">登出</mdui-button></a>
          </div>
        </mdui-card>
        <div class="stack">
          {private_panel(files, base)}
        </div>""",
            active="home",
            authed=True,
        )
    return page(
        "首頁",
        f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>CaveMan Drop</h1>
          <p>免帳號的匿名檔案分享。傳檔後立刻拿到永久連結。</p>
          <div class="form-row">
            <a href="/upload"><mdui-button>上傳檔案</mdui-button></a>
            <mdui-button variant="outlined" data-create-folder>建立空資料夾</mdui-button>
            <a href="/docs"><mdui-button variant="text">使用文件</mdui-button></a>
          </div>
        </mdui-card>
        <div class="stack">
          <mdui-card variant="outlined" class="card-pad">
            <h2>公開上傳</h2>
            <form action="/api/public/upload" method="post" enctype="multipart/form-data" data-ajax-upload>
              <div class="form-row">
                <input type="file" name="file" required>
                <mdui-button type="submit">上傳</mdui-button>
              </div>
            </form>
            <div data-upload-result></div>
          </mdui-card>
          <mdui-card variant="outlined" class="card-pad">
            <h2>私人空間</h2>
            <p>登入後可使用 16 線程分段上傳、私人檔案清單、預覽與刪除。</p>
            <a href="/login"><mdui-button>登入</mdui-button></a>
          </mdui-card>
          <div>
            <h2>端點一覽</h2>
            {endpoint_card("POST", "/api/public/upload", "匿名上傳。不帶 folder 會自動建立新的分享資料夾。", "/upload")}
            {endpoint_card("GET", "/f/{{folder_id}}", "資料夾瀏覽頁 — 把這個連結分享給別人。", "/upload")}
            {endpoint_card("GET", "/api", "機器可讀的 API 索引（程式拿 JSON）。", "/api")}
            {endpoint_card("GET", "/docs", "圖書館式指南與 API 參考。", "/docs")}
          </div>
        </div>""",
        active="home",
        authed=False,
    )


def _index_text(request: Request, authed: bool) -> str:
    base = str(request.base_url).rstrip("/")
    files = private_files() if authed else []
    lines = [
        "CaveMan Drop",
        "Text-only public file sharing and API server.",
        "",
        "Authentication:",
        f"  authenticated: {'yes' if authed else 'no'}",
        f"  login: POST {base}/login with form field password",
        f"  logout: GET {base}/logout",
        "",
        "Public API:",
        f"  POST {base}/api/public/folder",
        "    Create a public folder and receive its URLs.",
        f"  POST {base}/api/public/upload",
        "    Upload a file. Send multipart/form-data field 'file'. Optional form field 'folder' adds it to an existing folder.",
        f"  GET {base}/api/public/folder/<folder_id>",
        "    Return folder metadata, files, and download URLs.",
        f"  GET {base}/api/public/file/<folder_id>/<file_id>",
        "    Return one file's metadata and URL.",
        f"  GET {base}/dl/pub/<folder_id>/<file_id>",
        "    Download a public file.",
        f"  GET {base}/upload",
        "    Text description of the public upload API.",
        f"  GET {base}/f/<folder_id>",
        "    Text description and file listing for a public folder.",
        "",
        "Private API:",
        f"  GET {base}/api/files",
        "  POST /api/upload_chunk",
        "  POST /api/merge_chunks",
        "  GET /dl/<file_id>",
        "  GET /view/<file_id>",
        "  GET /del/<file_id>",
        "  These private endpoints require the existing authentication rules.",
        "",
        "Public limits:",
        f"  maximum file size: {settings.max_file_size // 1024**3} GB",
        f"  multi-file folder total: {settings.max_multi_folder_total // 1024**3} GB",
        f"  upload rate: {settings.rate_limit_max_uploads} attempts per IP per {settings.rate_limit_window // 3600} hour",
        "  CORS: enabled for public API requests",
        "",
        f"AI/API documentation: {base}/llms.txt",
    ]
    if authed:
        lines += ["", f"Private files currently visible: {len(files)}"]
    return "\n".join(lines)


@router.get("/")
async def index(request: Request):
    authed = bool(request.session.get("auth"))
    if wants_html(request):
        return HTMLResponse(_dashboard_html(request, authed))
    return PlainTextResponse(_index_text(request, authed))


def _login_html(error: str = "") -> str:
    err = f'<mdui-card variant="filled" class="card-pad"><p>{html.escape(error)}</p></mdui-card>' if error else ""
    return page(
        "登入",
        f"""{err}
        <mdui-card variant="outlined" class="card-pad">
          <h2>登入私人模式</h2>
          <p>登入後只會看到私人空間，不再顯示公開上傳。公開上傳不需要登入。</p>
          <form action="/login" method="post">
            <div class="form-row">
              <mdui-text-field type="password" name="password" label="密碼" required></mdui-text-field>
              <mdui-button type="submit">登入</mdui-button>
            </div>
          </form>
        </mdui-card>""",
        active="login",
    )


@router.get("/login")
async def login_get(request: Request):
    if wants_html(request):
        if request.session.get("auth"):
            return RedirectResponse("/", status_code=303)
        return HTMLResponse(_login_html())
    if request.session.get("auth"):
        return PlainTextResponse("Already authenticated. Use GET / for the server description.")
    return PlainTextResponse(
        "CaveMan Drop login\n\n"
        "This server is text/API only.\n"
        "Authenticate by POSTing a form field named 'password' to /login."
    )


@router.post("/login")
async def login_post(request: Request, password: str = Form(...)):
    if password == settings.password:
        request.session["auth"] = True
        if wants_html(request):
            return RedirectResponse("/", status_code=303)
        return PlainTextResponse("Login successful. GET / for the server description.")
    if wants_html(request):
        return HTMLResponse(_login_html("密碼錯誤，請再試一次。"), status_code=401)
    return PlainTextResponse("Wrong password.", status_code=401)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    if wants_html(request):
        return RedirectResponse("/", status_code=303)
    return PlainTextResponse("Logged out.")


def _upload_html() -> str:
    return page(
        "上傳",
        """
        <mdui-card variant="filled" class="card-pad hero">
          <h1>公開上傳</h1>
          <p>免帳號。上傳後立刻拿到永久連結。</p>
        </mdui-card>
        <div class="stack">
          <mdui-card variant="outlined" class="card-pad">
            <h2>上傳檔案</h2>
            <form action="/api/public/upload" method="post" enctype="multipart/form-data" data-ajax-upload>
              <div class="form-row">
                <input type="file" name="file" required>
                <mdui-text-field name="folder" label="資料夾 ID（選填，空白會建立新資料夾）"></mdui-text-field>
                <mdui-button type="submit">上傳</mdui-button>
              </div>
            </form>
            <div data-upload-result></div>
          </mdui-card>
          <mdui-card variant="outlined" class="card-pad">
            <h2>或先建立空資料夾</h2>
            <p>先建資料夾，再把連結分享給別人一起上傳。</p>
            <mdui-button data-create-folder>建立空資料夾</mdui-button>
          </mdui-card>
          <mdui-card variant="outlined" class="card-pad">
            <h2>curl 用法</h2>
            <pre class="curl">curl -F file=@example.bin /api/public/upload
curl -F file=@example.bin -F folder=FOLDER_ID /api/public/upload</pre>
          </mdui-card>
        </div>""",
        active="upload",
    )


def _upload_text(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return (
        "CaveMan Drop public upload\n\n"
        "No account is required.\n\n"
        "Upload one file:\n"
        f"  curl -F file=@example.bin {base}/api/public/upload\n\n"
        "The response contains:\n"
        "  folder_id\n"
        "  file_id\n"
        "  url\n"
        "  download_url\n"
        "  folder_url\n"
        "  folder_api_url\n\n"
        "Create an empty folder:\n"
        f"  curl -X POST {base}/api/public/folder\n\n"
        "Add a file to an existing folder:\n"
        f"  curl -F file=@example.bin -F folder=FOLDER_ID {base}/api/public/upload\n\n"
        f"Machine-readable API documentation: {base}/llms.txt"
    )


@router.get("/upload")
async def upload_page(request: Request):
    if request.session.get("auth"):
        # Private mode: no public upload — the dashboard has the private uploader.
        if wants_html(request):
            return RedirectResponse("/", status_code=303)
        return PlainTextResponse(_upload_text(request))
    if wants_html(request):
        return HTMLResponse(_upload_html())
    return PlainTextResponse(_upload_text(request))


def _folder_html(request: Request, folder_id: str) -> HTMLResponse | None:
    import os as _os

    from ..storage import public_folder_dir

    if not _os.path.isdir(public_folder_dir(folder_id)):
        return None
    base = str(request.base_url).rstrip("/")
    authed = bool(request.session.get("auth"))
    files = public_folder_files(folder_id)
    for f in files:
        f["download_url"] = f"{base}/dl/pub/{folder_id}/{f['id']}"
    rows = file_rows(files, folder_id, base)
    if authed:
        add_card = """
          <mdui-card variant="outlined" class="card-pad">
            <h2>加入檔案</h2>
            <p class="muted">目前為私人模式。如需上傳公開檔案，請先登出。</p>
            <a href="/logout"><mdui-button variant="outlined">登出以上傳公開檔案</mdui-button></a>
          </mdui-card>"""
    else:
        add_card = f"""
          <mdui-card variant="outlined" class="card-pad">
            <h2>加入檔案到此資料夾</h2>
            <form action="/api/public/upload" method="post" enctype="multipart/form-data" data-ajax-upload>
              <input type="hidden" name="folder" value="{html.escape(folder_id)}">
              <div class="form-row">
                <input type="file" name="file" required>
                <mdui-button type="submit">上傳</mdui-button>
              </div>
            </form>
            <div data-upload-result></div>
          </mdui-card>"""
    body = page(
        f"資料夾 {folder_id[:8]}",
        f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>公開資料夾</h1>
          <p><code>{html.escape(folder_id)}</code>
          <mdui-button variant="text" data-copy="{base}/f/{folder_id}">複製分享連結</mdui-button></p>
        </mdui-card>
        <div class="stack">
          <mdui-card variant="outlined" class="card-pad">
            <h2>檔案（{len(files)}）</h2>
            {rows}
          </mdui-card>
          {add_card}
        </div>""",
        active="upload",
        authed=authed,
    )
    return HTMLResponse(body)


def _folder_text(request: Request, folder_id: str) -> PlainTextResponse:
    import os as _os

    from ..storage import public_folder_dir

    if not _os.path.isdir(public_folder_dir(folder_id)):
        return PlainTextResponse("Folder not found.", status_code=404)
    base = str(request.base_url).rstrip("/")
    files = public_folder_files(folder_id)
    lines = [
        "CaveMan Drop public folder",
        f"folder_id: {folder_id}",
        f"folder_url: {base}/f/{folder_id}",
        f"upload_url: {base}/f/{folder_id}",
        f"api_url: {base}/api/public/folder/{folder_id}",
        "",
        "Anyone with this folder ID can add a file through the public upload API.",
        f"Upload: curl -F file=@example.bin -F folder={folder_id} {base}/api/public/upload",
        "",
        f"Files: {len(files)}",
    ]
    if not files:
        lines.append("  No files in this folder.")
    else:
        for f in files:
            lines += [
                "",
                f"  {f['name']}",
                f"    file_id: {f['id']}",
                f"    size_bytes: {f['size']}",
                f"    content_type: {f['content_type']}",
                f"    url: {base}/dl/pub/{folder_id}/{f['id']}",
                f"    api: {base}/api/public/file/{folder_id}/{f['id']}",
            ]
    return PlainTextResponse("\n".join(lines))


@router.get("/f/{folder_id}")
async def folder_page(request: Request, folder_id: str):
    if wants_html(request):
        html_resp = _folder_html(request, folder_id)
        if html_resp is None:
            return HTMLResponse(
                page("找不到", '<mdui-card class="card-pad"><p>找不到這個資料夾。</p></mdui-card>'),
                status_code=404,
            )
        return html_resp
    return _folder_text(request, folder_id)
