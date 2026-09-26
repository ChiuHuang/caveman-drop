"""Smoke test: browser HTML vs agent text/JSON, upload flows, private mode."""
import uuid

from fastapi.testclient import TestClient
from app import app

c = TestClient(app)
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
     "Accept": "text/html,application/xhtml+xml"}
J = {"User-Agent": "curl/8.0", "Accept": "*/*"}

# --- logged-out: public UI visible ---
r = c.get("/", headers=B)
print("browser /:", r.status_code, r.headers["content-type"], "mdui" in r.text.lower())
assert "data-chunked" in r.text and "data-tp" in r.text
assert "16 線程" not in r.text and "瀏覽器使用圖形介面" not in r.text
r = c.get("/", headers=J)
print("curl /:", r.status_code, r.text.splitlines()[0])
assert r.text.startswith("CaveMan Drop")

r = c.get("/api", headers=J)
print("curl /api:", r.status_code, sorted(r.json().keys()))
r = c.get("/api", headers=B)
assert "API 索引" in r.text
print("browser /api OK")

r = c.get("/llms.txt", headers=J)
assert r.text.startswith("# CaveMan Drop")
print("llms OK")

r = c.get("/upload", headers=B)
assert "data-chunked" in r.text and "data-tp-segs" in r.text
print("browser /upload OK (thread panel present)")

r = c.get("/docs", headers=B)
assert "docs-layout" in r.text
print("browser /docs OK")
r = c.get("/docs/api", headers=J)
assert r.text.startswith("# API 參考")
print("curl /docs/api OK")

# --- public upload + folder + download + preview ---
f = c.post("/api/public/upload", headers=J, files={"file": ("hello.txt", b"hi caveman")})
assert f.status_code == 200
fid, folder = f.json()["file_id"], f.json()["folder_id"]
print("upload OK:", f.json()["filename"], f.json()["size_bytes"])

g = c.get(f"/api/public/folder/{folder}", headers=J)
assert g.status_code == 200 and len(g.json()["files"]) == 1
g = c.get(f"/api/public/folder/{folder}", headers=B)
assert "data-mt-download" in g.text and "data-preview" in g.text
assert "16 線程下載" not in g.text
print("folder json+html OK")

d = c.get(f"/dl/pub/{folder}/{fid}", headers=J)
assert d.status_code == 200 and d.content == b"hi caveman"
assert "attachment" in d.headers["content-disposition"]
p = c.get(f"/dl/pub/{folder}/{fid}?preview=1", headers=J)
assert "inline" in p.headers["content-disposition"]
print("download + preview-disposition OK")

h = c.get(f"/f/{folder}", headers=B)
assert "公開資料夾" in h.text and "加入檔案到此資料夾" in h.text
print("share page OK")

# --- public 16-thread chunked upload (everyone, no login) ---
puid = str(uuid.uuid4())
pblob = b"y" * 1000
for i in range(2):
    rr = c.post("/api/public/chunk", headers=J,
                files={"file_chunk": ("c", pblob if i == 0 else b"z")},
                data={"upload_id": puid, "index": str(i), "filename": "pub.bin"})
    assert rr.status_code == 200, rr.text
    assert rr.json()["threads"] == 16 and not rr.json()["throttled"]
m = c.post("/api/public/merge_chunks", headers=J,
           json={"upload_id": puid, "filename": "pub.bin", "total_chunks": 2})
assert m.status_code == 200 and m.json()["size_bytes"] == 1001
pfid, pfold = m.json()["file_id"], m.json()["folder_id"]
d = c.get(f"/dl/pub/{pfold}/{pfid}", headers=J)
assert d.content == pblob + b"z"
print("public chunked upload+merge OK")

# --- bandwidth tiers: 100MB->90, 1GB->80 ... floor 40, reset per window ---
from app import storage as _st
assert _st.throttle_mbps_for(50 * 1024 * 1024) is None
assert _st.throttle_mbps_for(150 * 1024 * 1024) == 90
assert _st.throttle_mbps_for(int(1.2 * 1024**3)) == 80
assert _st.throttle_mbps_for(int(2.5 * 1024**3)) == 70
assert _st.throttle_mbps_for(int(9 * 1024**3)) == 40
_st.bw_record("9.9.9.9", None, 150 * 1024 * 1024)
st = _st.bw_status("9.9.9.9")
assert st["throttled"] and st["threads"] == 16 and st["throttle_mbps"] == 90
st2 = _st.bw_status("8.8.8.8")
assert not st2["throttled"] and st2["threads"] == 16
print("bandwidth tiers OK")

# --- CF real IP: chunk recorded under CF-Connecting-IP, not peer ---
rr = c.post("/api/public/chunk", headers={**J, "CF-Connecting-IP": "1.2.3.4"},
            files={"file_chunk": ("c", b"cf")},
            data={"upload_id": str(uuid.uuid4()), "index": "0", "filename": "cf.bin"})
assert rr.status_code == 200
assert _st.bw_total("ip:1.2.3.4") == 2
print("CF real IP OK")

# --- login -> private mode, public upload hidden ---
# Push the test IP over budget first: private session must stay exempt.
_st.bw_record("testclient", None, 200 * 1024 * 1024)
r = c.post("/login", headers=J, data={"password": "passw"})
assert r.status_code == 200
print("login OK")

r = c.get("/", headers=B)
assert "私人模式" in r.text and "data-chunked" in r.text
assert "/api/public/chunk" not in r.text, "public upload must be hidden when logged in"
print("private-mode dashboard OK")

r = c.get("/upload", headers=B, follow_redirects=False)
assert r.status_code == 303, "logged-in /upload should redirect to /"
print("logged-in /upload redirect OK")

h = c.get(f"/f/{folder}", headers=B)
assert "私人模式" in h.text and "加入檔案到此資料夾" not in h.text
print("folder page hides upload form when logged in OK")

# --- 16-thread style chunked upload (sequential here, same endpoints) ---
uid = str(uuid.uuid4())
blob = b"x" * (3 * 1024 * 1024 + 17)
CS = 4 * 1024 * 1024
total = (len(blob) + CS - 1) // CS
for i in range(total):
    rr = c.post("/api/upload_chunk", headers=J, files={"file_chunk": ("c", blob[i*CS:(i+1)*CS])},
                data={"upload_id": uid, "index": str(i), "filename": "big.bin"})
    assert rr.status_code == 200, rr.text
    assert rr.json().get("exempt") is True and rr.json()["threads"] == 16
m = c.post("/api/merge_chunks", headers=J, json={"upload_id": uid, "filename": "big.bin", "total_chunks": total})
assert m.json()["success"]
priv_id = m.json()["file_id"]
print("chunked upload+merge OK:", total, "chunk(s)")

r = c.get("/api/files", headers=J)
names = [x["name"] for x in r.json()["files"]]
assert "big.bin" in names
r = c.get("/", headers=B)
assert "big.bin" in r.text and "直接連結" in r.text and "刪除" in r.text and "預覽" in r.text
print("private file row buttons OK")

dl = c.get(f"/dl/{priv_id}", headers={**J, "Range": "bytes=0-99"})
assert dl.status_code == 206 and dl.headers["Content-Range"].startswith("bytes 0-99/")
print("range download OK")

v = c.get(f"/view/{priv_id}", headers=J)
assert v.status_code == 200
print("preview view OK")

print("ALL_SMOKE_OK")
