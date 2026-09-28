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
from ..storage import (
    get_private_folders,
    get_shares,
    private_files,
    public_files,
    public_folder_files,
    public_folder_list,
    public_folder_name,
    short_code,
)
from ..i18n import lang_for, t
from ..ui import file_rows, page, private_panel, public_upload_form
from ..auth import authed
from ..urls import base_url

router = APIRouter()


def _dashboard_html(request: Request, is_signed_in: bool) -> str:
    base = base_url(request)
    lang = lang_for(request)
    if is_signed_in:
        return page(
            t(lang, "private_h1"),
            f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(t(lang, "private_h1"))}</h1>
          <p>{html.escape(t(lang, "private_logged_in"))}</p>
          <div class="form-row">
            <a href="/api/files"><mdui-button variant="outlined">{html.escape(t(lang, "files_api"))}</mdui-button></a>
            <a href="/logout"><mdui-button variant="text">{html.escape(t(lang, "nav_logout"))}</mdui-button></a>
          </div>
        </mdui-card>
        <div class="stack">
          {private_panel(
            lang, private_files(), base, get_private_folders(), get_shares(),
            public_files(), public_folder_list(),
          )}
        </div>""",
            active="home",
            authed=True,
            lang=lang,
        )
    return page(
        t(lang, "nav_home"),
        f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>CaveMan Drop</h1>
          <p>{html.escape(t(lang, "tagline"))}</p>
          <div class="form-row">
            <a href="/docs"><mdui-button variant="text">{html.escape(t(lang, "home_docs"))}</mdui-button></a>
            <a href="/login"><mdui-button variant="outlined">{html.escape(t(lang, "home_login"))}</mdui-button></a>
          </div>
        </mdui-card>
        <div class="stack">
          <mdui-card variant="outlined" class="card-pad">
            <h2>{html.escape(t(lang, "public_upload_h"))}</h2>
            {public_upload_form(lang)}
          </mdui-card>
        </div>""",
        active="home",
        authed=False,
        lang=lang,
    )


def _index_text(request: Request, authed: bool) -> str:
    base = base_url(request)
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
        "    Upload a file. Send multipart/form-data field 'file'. Optional form field 'folder' is an existing folder_id, or free text to name a new folder.",
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
        f"  maximum file size: {settings.max_file_size // 1024**3} GB (public; private uncapped)",
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
    signed_in = authed(request)
    if wants_html(request):
        return HTMLResponse(_dashboard_html(request, signed_in))
    return PlainTextResponse(_index_text(request, signed_in))


def _login_html(request: Request, error: str = "") -> str:
    lang = lang_for(request)
    err = (
        f'<mdui-card variant="filled" class="card-pad"><p>{html.escape(error)}</p></mdui-card>'
        if error
        else ""
    )
    return page(
        t(lang, "nav_login"),
        f"""{err}
        <mdui-card variant="outlined" class="card-pad">
          <h2>{html.escape(t(lang, "login_h"))}</h2>
          <p>{html.escape(t(lang, "login_p"))}</p>
          <form action="/login" method="post">
            <div class="form-row">
              <mdui-text-field type="password" name="password" label="{html.escape(t(lang, "login_pw"))}" required></mdui-text-field>
              <mdui-button type="submit">{html.escape(t(lang, "login_btn"))}</mdui-button>
            </div>
          </form>
        </mdui-card>""",
        active="login",
        lang=lang,
    )


@router.get("/login")
async def login_get(request: Request):
    if authed(request):
        # ?auth=<PASSWORD> works too; set the cookie and drop the secret from the URL
        request.session["auth"] = True
        if wants_html(request):
            return RedirectResponse("/", status_code=303)
        return PlainTextResponse("Already authenticated. Use GET / for the server description.")
    if wants_html(request):
        return HTMLResponse(_login_html(request))
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
    lang = lang_for(request)
    if wants_html(request):
        return HTMLResponse(_login_html(request, t(lang, "login_err")), status_code=401)
    return PlainTextResponse("Wrong password.", status_code=401)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    if wants_html(request):
        return RedirectResponse("/", status_code=303)
    return PlainTextResponse("Logged out.")


def _upload_html(request: Request) -> str:
    lang = lang_for(request)
    return page(
        t(lang, "nav_upload"),
        f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(t(lang, "upload_h1"))}</h1>
          <p>{html.escape(t(lang, "tagline"))}</p>
        </mdui-card>
        <div class="stack">
          <mdui-card variant="outlined" class="card-pad">
            <h2>{html.escape(t(lang, "upload_files_h"))}</h2>
            {public_upload_form(lang)}
          </mdui-card>
          <mdui-card variant="outlined" class="card-pad">
            <h2>{html.escape(t(lang, "curl_h"))}</h2>
            <pre class="curl">curl -F file=@example.bin /api/public/upload
curl -F file=@example.bin -F folder=FOLDER_ID /api/public/upload
curl -F file=@example.bin -F folder=my-folder /api/public/upload</pre>
          </mdui-card>
        </div>""",
        active="upload",
        lang=lang,
    )


def _upload_text(request: Request) -> str:
    base = base_url(request)
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
        f"  curl -F file=@example.bin -F folder=FOLDER_ID {base}/api/public/upload\n"
        "  (`folder` also takes free text: a name creates a new folder with that name)\n\n"
        f"Machine-readable API documentation: {base}/llms.txt"
    )


@router.get("/upload")
async def upload_page(request: Request):
    if authed(request):
        # Private mode: no public upload — the dashboard has the private uploader.
        if wants_html(request):
            return RedirectResponse("/", status_code=303)
        return PlainTextResponse(_upload_text(request))
    if wants_html(request):
        return HTMLResponse(_upload_html(request))
    return PlainTextResponse(_upload_text(request))


def _folder_html(request: Request, folder_id: str) -> HTMLResponse | None:
    import os as _os

    from ..storage import public_folder_dir

    if not _os.path.isdir(public_folder_dir(folder_id)):
        return None
    base = base_url(request)
    lang = lang_for(request)
    is_signed_in = authed(request)
    files = public_folder_files(folder_id)
    for f in files:
        f["download_url"] = f"{base}/dl/pub/{folder_id}/{f['id']}"
        f["short_url"] = f"{base}/usercontent/{short_code(f['id'])}{f.get('ext', '')}"
    rows = file_rows(lang, files, folder_id, base)
    title = public_folder_name(folder_id) or t(lang, "unnamed_folder")
    if is_signed_in:
        add_card = f"""
          <mdui-card variant="outlined" class="card-pad">
            <h2>{html.escape(t(lang, "add_here_h"))}</h2>
            <p class="muted">{html.escape(t(lang, "private_mode_note"))}</p>
            <a href="/logout"><mdui-button variant="outlined">{html.escape(t(lang, "signout_first"))}</mdui-button></a>
          </mdui-card>"""
    else:
        add_card = f"""
          <mdui-card variant="outlined" class="card-pad">
            <h2>{html.escape(t(lang, "add_here_h"))}</h2>
            {public_upload_form(lang, folder_id)}
          </mdui-card>"""
    body = page(
        title,
        f"""
        <mdui-card variant="filled" class="card-pad hero">
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(t(lang, "folder_public", n=len(files)))}
          <mdui-button variant="text" data-copy="{base}/f/{folder_id}">{html.escape(t(lang, "copy_share"))}</mdui-button></p>
        </mdui-card>
        <div class="stack">
          <mdui-card variant="outlined" class="card-pad">
            <h2>{html.escape(t(lang, "files_h", n=len(files)))}</h2>
            {rows}
          </mdui-card>
          {add_card}
        </div>""",
        active="upload",
        authed=is_signed_in,
        lang=lang,
    )
    return HTMLResponse(body)


def _folder_text(request: Request, folder_id: str) -> PlainTextResponse:
    import os as _os

    from ..storage import public_folder_dir

    if not _os.path.isdir(public_folder_dir(folder_id)):
        return PlainTextResponse("Folder not found.", status_code=404)
    base = base_url(request)
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
            lang = lang_for(request)
            return HTMLResponse(
                page(
                    t(lang, "not_found"),
                    '<mdui-card class="card-pad"><p>' + html.escape(t(lang, "not_found_folder")) + "</p></mdui-card>",
                    lang=lang,
                ),
                status_code=404,
            )
        return html_resp
    return _folder_text(request, folder_id)
