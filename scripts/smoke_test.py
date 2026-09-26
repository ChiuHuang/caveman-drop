"""Smoke test: browser HTML vs agent text/JSON, upload flows, private mode."""
import os
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
assert "建立空資料夾" not in r.text and '<a href="/upload"><mdui-button>' not in r.text
print("hero cleaned OK")
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
assert "先說好" in r.text
assert "建立資料夾" in r.text and "data-tabs" in r.text
print("browser /upload OK (thread panel present)")

r = c.get("/docs", headers=B)
assert "docs-layout" in r.text
print("browser /docs OK")
r = c.get("/docs/api", headers=J)
assert r.text.startswith("# API 參考")
print("curl /docs/api OK")

# --- single upload: direct link, NO folder created ---
import glob as _glob
_before = set(_glob.glob("public_uploads/*"))
f = c.post("/api/public/upload", headers=J, files={"file": ("hello.txt", b"hi caveman")})
assert f.status_code == 200
assert "folder_id" not in f.json() and "folder_url" not in f.json()
fid = f.json()["file_id"]
print("single upload OK:", f.json()["filename"], f.json()["size_bytes"])
assert set(_glob.glob("public_uploads/*")) == _before, "single upload must not create a folder"
d = c.get(f"/dl/s/{fid}", headers=J)
assert d.status_code == 200 and d.content == b"hi caveman"
assert "attachment" in d.headers["content-disposition"]
m = c.get(f"/api/public/single/{fid}", headers=J)
assert m.json()["filename"] == "hello.txt"
p = c.get(f"/dl/s/{fid}?preview=1", headers=J)
assert "inline" in p.headers["content-disposition"]
print("single download + metadata OK")

# --- folder flow: explicit create with name, then join ---
cf = c.post("/api/public/folder", headers=J, json={"name": "派對"})
assert cf.status_code == 200 and cf.json()["folder_name"] == "派對"
folder = cf.json()["folder_id"]
f2 = c.post("/api/public/upload", headers=J, files={"file": ("j.txt", b"joined")}, data={"folder": folder})
assert f2.json()["folder_id"] == folder
jfid = f2.json()["file_id"]

g = c.get(f"/api/public/folder/{folder}", headers=J)
assert g.status_code == 200 and len(g.json()["files"]) == 1
g = c.get(f"/api/public/folder/{folder}", headers=B)
assert "data-mt-download" in g.text and "data-preview" in g.text
assert "16 線程下載" not in g.text
print("folder json+html OK")

d = c.get(f"/dl/pub/{folder}/{jfid}", headers=J)
assert d.status_code == 200 and d.content == b"joined"
print("folder download OK")

h = c.get(f"/f/{folder}", headers=B)
assert "公開資料夾" in h.text and "加入檔案到此資料夾" in h.text
assert "派對" in h.text and "<code>" not in h.text
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
assert "folder_id" not in m.json(), "chunked merge without folder must stay single"
pfid = m.json()["file_id"]
d = c.get(f"/dl/s/{pfid}", headers=J)
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

# --- high chunk indices accepted (big files) ---
big_uid = str(uuid.uuid4())
rr = c.post("/api/public/chunk", headers=J, files={"file_chunk": ("c", b"hi")},
            data={"upload_id": big_uid, "index": "2048", "filename": "huge.bin"})
assert rr.status_code == 200, rr.text
import shutil
shutil.rmtree(f"airdrop_tmp/pub_{big_uid}", ignore_errors=True)
print("high chunk index OK")

# --- 1MB probe tags the real IP with a thread count ---
probe_body = b"p" * (1024 * 1024)
pr = c.post("/api/public/probe", headers={**J, "CF-Connecting-IP": "5.6.7.8"},
            files={"probe": ("probe.bin", probe_body)})
assert pr.status_code == 200, pr.text
assert pr.json()["you"] == "5.6.7.8" and pr.json()["threads"] == 16
rr = c.post("/api/public/chunk", headers={**J, "CF-Connecting-IP": "5.6.7.8"},
            files={"file_chunk": ("c", b"z")},
            data={"upload_id": str(uuid.uuid4()), "index": "0", "filename": "t.bin"})
assert rr.json()["threads_tagged"] == 16
from app.storage import threads_for_speed
assert threads_for_speed(1024 * 1024) == 128 and threads_for_speed(20 * 1024 * 1024) == 16
print("probe + IP tag OK")

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
assert "data-sortbar" in r.text and "data-sort-size" in r.text
print("private file row buttons OK")

dl = c.get(f"/dl/{priv_id}", headers={**J, "Range": "bytes=0-99"})
assert dl.status_code == 206 and dl.headers["Content-Range"].startswith("bytes 0-99/")
print("range download OK")

# --- private cloud folders: mkdir, upload into it, deldir ---
mf = c.post("/api/folders", headers=J, json={"name": "工作"})
assert mf.status_code == 200
pfolder = mf.json()["folder_id"]
uid2 = str(uuid.uuid4())
c.post("/api/upload_chunk", headers=J, files={"file_chunk": ("c", b"data")},
       data={"upload_id": uid2, "index": "0", "filename": "w.txt"})
m2 = c.post("/api/merge_chunks", headers=J,
            json={"upload_id": uid2, "filename": "w.txt", "total_chunks": 1, "folder_id": pfolder})
assert m2.json()["success"]
wfid = m2.json()["file_id"]
fl = c.get("/api/folders", headers=J)
assert any(x["id"] == pfolder and x["count"] == 1 for x in fl.json()["folders"])
r = c.get("/", headers=B)
assert "工作" in r.text and "data-delete-dir" in r.text and "未分類" in r.text
assert "建立檢視連結" in r.text and "建立上傳連結" in r.text

# --- share folder: view-only vs upload ---
sv = c.post(f"/api/folders/{pfolder}/share", headers=J, json={"mode": "view"})
assert sv.status_code == 200
vtok = sv.json()["token"]
su = c.post(f"/api/folders/{pfolder}/share", headers=J, json={"mode": "upload"})
utok = su.json()["token"]
assert su.json()["url"].endswith(f"/s/{utok}")

sp = c.get(f"/s/{vtok}", headers=B)
assert "工作" in sp.text and "w.txt" in sp.text and "僅檢視" in sp.text
assert "上傳到此資料夾" not in sp.text
sp = c.get(f"/s/{utok}", headers=B)
assert "可上傳" in sp.text and "上傳到此資料夾" in sp.text
sp = c.get(f"/s/{vtok}", headers=J)
assert "mode: view" in sp.text

vd = c.get(f"/dl/sh/{vtok}/{wfid}", headers=J)
assert vd.status_code == 200 and vd.content == b"data"

uid3 = str(uuid.uuid4())
c.post("/api/public/chunk", headers=J, files={"file_chunk": ("c", b"shared")},
       data={"upload_id": uid3, "index": "0", "filename": "s.txt"})
bad = c.post("/api/share/merge_chunks", headers=J,
             json={"upload_id": uid3, "filename": "s.txt", "total_chunks": 1, "token": vtok})
assert bad.status_code == 403, "view-only link must not upload"
good = c.post("/api/share/merge_chunks", headers=J,
              json={"upload_id": uid3, "filename": "s.txt", "total_chunks": 1, "token": utok})
assert good.status_code == 200
sd = c.get(f"/dl/sh/{utok}/{good.json()['file_id']}", headers=J)
assert sd.content == b"shared"

rv = c.post("/api/share/revoke", headers=J, json={"token": vtok})
assert rv.status_code == 200
assert c.get(f"/s/{vtok}", headers=J).status_code == 404
print("share view/upload/revoke OK")

d = c.get(f"/deldir/{pfolder}", headers=J)
assert d.json()["deleted_files"] == 2
fl = c.get("/api/folders", headers=J)
assert all(x["id"] != pfolder for x in fl.json()["folders"])
assert c.get(f"/s/{utok}", headers=J).status_code == 404, "deleting folder kills its shares"
print("private folders OK")

v = c.get(f"/view/{priv_id}", headers=J)
assert v.status_code == 200
print("preview view OK")

# --- private merge uncapped: tiny cap rejects, None assembles ---
import tempfile
from fastapi import HTTPException
from app.storage import assemble_chunks
tmp = tempfile.mkdtemp()
os.makedirs(f"{tmp}/parts", exist_ok=True)
open(f"{tmp}/parts/part_0", "wb").write(b"0123456789")
try:
    assemble_chunks(f"{tmp}/parts", f"{tmp}/out", 1, 5)
    raise SystemExit("cap should have rejected")
except HTTPException as e:
    assert e.status_code == 413
open(f"{tmp}/parts/part_0", "wb").write(b"0123456789")
n = assemble_chunks(f"{tmp}/parts", f"{tmp}/out", 1, None)
assert n == 10
print("private uncapped assemble OK")

# --- tmp sweeper: stale chunk dirs removed, fresh kept ---
import time
from app.config import settings as _settings
from app.storage import sweep_tmp
old_age = _settings.tmp_max_age_hours
_settings.tmp_max_age_hours = 24
stale = os.path.join(_settings.tmp_dir, "sweep_test_stale")
fresh = os.path.join(_settings.tmp_dir, "sweep_test_fresh")
os.makedirs(stale, exist_ok=True)
os.makedirs(fresh, exist_ok=True)
open(os.path.join(stale, "part_0"), "wb").write(b"x")
open(os.path.join(fresh, "part_0"), "wb").write(b"x")
past = time.time() - 2 * 86400
os.utime(os.path.join(stale, "part_0"), (past, past))
os.utime(stale, (past, past))
assert sweep_tmp() >= 1
assert not os.path.exists(stale) and os.path.exists(fresh)
import shutil
shutil.rmtree(fresh, ignore_errors=True)
_settings.tmp_max_age_hours = old_age
print("tmp sweep OK")

print("ALL_SMOKE_OK")
