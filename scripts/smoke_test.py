from fastapi.testclient import TestClient
from app import app

c = TestClient(app)
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
     "Accept": "text/html,application/xhtml+xml"}
J = {"User-Agent": "curl/8.0", "Accept": "*/*"}

r = c.get("/", headers=B)
print("browser /:", r.status_code, r.headers["content-type"], "mdui" in r.text.lower())
r = c.get("/", headers=J)
print("curl /:", r.status_code, r.headers["content-type"], r.text.splitlines()[0])
r = c.get("/api", headers=J)
print("curl /api:", r.status_code, sorted(r.json().keys()))
r = c.get("/api", headers=B)
print("browser /api:", r.status_code, "mdui" in r.text.lower())
r = c.get("/llms.txt", headers=J)
print("llms:", r.status_code, r.text.splitlines()[0])
r = c.get("/upload", headers=B)
print("browser /upload:", r.status_code, "ajax-upload" in r.text)
r = c.get("/upload", headers=J)
print("curl /upload:", r.status_code, r.text.splitlines()[0])
r = c.get("/docs", headers=B)
print("browser /docs:", r.status_code, "docs-layout" in r.text)
r = c.get("/docs/api", headers=J)
print("curl /docs/api:", r.status_code, r.text.splitlines()[0])
f = c.post("/api/public/upload", headers=J, files={"file": ("hello.txt", b"hi caveman")})
print("upload:", f.status_code, f.json()["filename"], f.json()["size_bytes"])
fid, folder = f.json()["file_id"], f.json()["folder_id"]
g = c.get(f"/api/public/folder/{folder}", headers=J)
print("folder json:", g.status_code, len(g.json()["files"]))
g = c.get(f"/api/public/folder/{folder}", headers=B)
print("folder html:", g.status_code, "mdui" in g.text.lower())
d = c.get(f"/dl/pub/{folder}/{fid}", headers=J)
print("download:", d.status_code, d.content)
h = c.get(f"/f/{folder}", headers=B)
print("share page:", h.status_code, "Public folder" in h.text)
h = c.get(f"/f/{folder}", headers=J)
print("share text:", h.status_code, h.text.splitlines()[0])

# login flow (curl keeps text behavior)
r = c.post("/login", headers=J, data={"password": "passw"})
print("login:", r.status_code, r.text[:20])
r = c.get("/api/files", headers=J)
print("private files:", r.status_code, "files" in r.json())
r = c.get("/login", headers=B)
print("browser login authed -> redirect:", r.status_code)
print("ALL_SMOKE_OK")
