"""Smoke test: browser HTML vs agent text/JSON, upload flows, private mode."""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
import hashlib
from app.storage import bin_path

_before = set(_glob.glob("public_uploads/*"))
_want = hashlib.sha256(b"hi caveman").hexdigest()
if os.path.exists(bin_path(_want)):  # start from a clean bin for this content
    os.remove(bin_path(_want))
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

# --- content addressing: file_id is the sha256, same bytes = one stored copy ---
assert fid == _want, (fid, _want)
assert not f.json()["deduplicated"], "first copy must actually be stored"
f_again = c.post("/api/public/upload", headers=J, files={"file": ("hello.txt", b"hi caveman")})
assert f_again.json()["file_id"] == fid, "same content must reuse the same id"
assert f_again.json()["deduplicated"] is True
assert c.get(f"/dl/s/{fid}", headers=J).content == b"hi caveman"
# same bytes, different name + a folder: still one blob, two entries
f3 = c.post("/api/public/upload", headers=J, files={"file": ("copy.txt", b"hi caveman")}, data={"folder": "去重"})
dup = f3.json()["file_id"]
assert dup == fid and f3.json()["deduplicated"] is True and f3.json()["folder_id"]
assert os.path.exists(bin_path(fid))
assert len([n for n in os.listdir(os.path.dirname(bin_path(fid))) if n == fid]) == 1
print("sha256 ids + bin dedupe OK")

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
assert pfid == hashlib.sha256(pblob + b"z").hexdigest(), "merged file_id must be the content sha256"
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

# --- scheme follows the request: https in -> https links out ---
r = c.get("/api", headers=J)
assert r.json()["endpoints"]["download"]["url"].startswith("http://testserver"), r.json()["endpoints"]["download"]["url"]
fwd = {**J, "X-Forwarded-Proto": "https", "X-Forwarded-Host": "file.chiuhuang.dev"}
r = c.get("/api", headers=fwd)
assert r.json()["endpoints"]["single_download"]["url"] == "https://file.chiuhuang.dev/dl/s/{file_id}", r.json()["endpoints"]["single_download"]["url"]
r = c.get("/llms.txt", headers=fwd)
assert "https://file.chiuhuang.dev/api/public/upload" in r.text
r = c.post("/api/public/upload", headers=fwd, files={"file": ("s.txt", b"secure")})
assert r.json()["download_url"].startswith("https://file.chiuhuang.dev/dl/s/")
r = c.post("/api/public/folder", headers=fwd, json={"name": "派對2"})
assert r.json()["folder_url"].startswith("https://file.chiuhuang.dev/f/")
r = c.get(f"/f/{folder}", headers={**B, "X-Forwarded-Proto": "https", "X-Forwarded-Host": "file.chiuhuang.dev"})
assert f'data-copy="https://file.chiuhuang.dev/f/{folder}"' in r.text
assert "http://" not in r.text
r = c.post("/api/public/upload", headers=J, files={"file": ("f.txt", b"fwd")})
assert r.json()["download_url"].startswith("http://testserver/"), "plain http request must stay http"
print("https/http base_url OK")

from app.config import settings as _cfg
_old_base = _cfg.public_base_url
_cfg.public_base_url = "https://fixed.example.com"
try:
    r = c.get("/api", headers={**J, "X-Forwarded-Proto": "https", "X-Forwarded-Host": "evil.test"})
    assert r.json()["endpoints"]["upload"]["url"] == "https://fixed.example.com/api/public/upload"
finally:
    _cfg.public_base_url = _old_base
print("PUBLIC_BASE_URL override OK")

# --- forwarded header edge cases (app.urls) ---
from starlette.requests import Request as _Request
from app.urls import base_url as _base_url


def _fake_request(headers):
    hdrs = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return _Request({"type": "http", "http_version": "1.1", "method": "GET", "scheme": "http",
                     "path": "/", "raw_path": b"/", "query_string": b"", "root_path": "",
                     "headers": hdrs, "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 20042)})


assert _base_url(_fake_request({"host": "a.test"})) == "http://a.test"
assert _base_url(_fake_request({"host": "a.test", "x-forwarded-proto": "https, http"})) == "https://a.test"
assert _base_url(_fake_request({"host": "a.test", "x-forwarded-ssl": "on"})) == "https://a.test"
assert _base_url(_fake_request({"host": "a.test", "forwarded": "proto=https;host=cdn.test"})) == "https://cdn.test"
assert _base_url(_fake_request({"host": "a.test", "x-forwarded-proto": "gopher"})) == "http://a.test"
assert _base_url(_fake_request({"host": "a.test", "x-forwarded-host": "evil.test/p"})) == "http://a.test"
print("forwarded header edge cases OK")

# --- folder field accepts an id OR a free-text name ---
byname = c.post("/api/public/upload", headers=J, files={"file": ("n.txt", b"named")}, data={"folder": "我的相簿"})
assert byname.status_code == 200, byname.text
assert byname.json()["folder_name"] == "我的相簿"
named_folder = byname.json()["folder_id"]
g = c.get(f"/api/public/folder/{named_folder}", headers=J)
assert [f["name"] for f in g.json()["files"]] == ["n.txt"]
h = c.get(f"/f/{named_folder}", headers=B)
assert "我的相簿" in h.text
nuid = str(uuid.uuid4())
c.post("/api/public/chunk", headers=J, files={"file_chunk": ("c", b"chunked-name")},
       data={"upload_id": nuid, "index": "0", "filename": "cn.txt"})
mn = c.post("/api/public/merge_chunks", headers=J,
            json={"upload_id": nuid, "filename": "cn.txt", "total_chunks": 1, "folder": "合併資料夾"})
assert mn.json()["folder_name"] == "合併資料夾" and mn.json()["folder_url"].startswith("http://testserver/f/")
print("folder name as text OK")

# --- 1MB probe tags the real IP with a thread count ---
probe_body = b"p" * (1024 * 1024)
pr = c.post("/api/public/probe", headers={**J, "CF-Connecting-IP": "5.6.7.8"},
            files={"probe": ("probe.bin", probe_body)})
assert pr.status_code == 200, pr.text
assert pr.json()["you"] == "5.6.7.8" and pr.json()["threads"] == 16
# a client that measured 1s for the probe is slow -> more threads
slow = c.post("/api/public/probe", headers={**J, "CF-Connecting-IP": "5.6.7.9"},
              files={"probe": ("probe.bin", probe_body)}, data={"ms": "1000"})
assert slow.json()["threads"] == 128 and abs(slow.json()["mbps"] - 8.39) < 0.01, slow.json()
# bogus client timing is ignored, server-side timing used instead
bogus = c.post("/api/public/probe", headers={**J, "CF-Connecting-IP": "5.6.7.10"},
               files={"probe": ("probe.bin", probe_body)}, data={"ms": "abc"})
assert bogus.json()["threads"] == 16
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

# --- private uncapped assemble + sha256 id OK (already printed above) ---
# --- private merge uncapped: tiny cap rejects, None assembles ---
import tempfile
from fastapi import HTTPException
from app.storage import assemble_chunks, bin_path
tmp = tempfile.mkdtemp()
os.makedirs(f"{tmp}/parts", exist_ok=True)
open(f"{tmp}/parts/part_0", "wb").write(b"0123456789")
try:
    assemble_chunks(f"{tmp}/parts", 1, 5, staging=tmp)
    raise SystemExit("cap should have rejected")
except HTTPException as e:
    assert e.status_code == 413
os.makedirs(f"{tmp}/parts", exist_ok=True)
open(f"{tmp}/parts/part_0", "wb").write(b"0123456789")
fid10, n = assemble_chunks(f"{tmp}/parts", 1, None, staging=tmp)
assert n == 10
assert fid10 == hashlib.sha256(b"0123456789").hexdigest(), fid10
assert os.path.exists(bin_path(fid10)), "assembled blob must land in the bin store"
print("private uncapped assemble + sha256 id OK")

# --- legacy UUID file ids still resolve (old links keep working) ---
legacy_id = str(uuid.uuid4())
open(os.path.join("airdrop_files", legacy_id + ".txt"), "wb").write(b"legacy")
import json as _json
with open(os.path.join("airdrop_files", legacy_id + ".json"), "w", encoding="utf-8") as f:
    _json.dump({"filename": "old.txt", "ext": ".txt"}, f)
ld = c.get(f"/dl/{legacy_id}", headers=J)
assert ld.status_code == 200 and ld.content == b"legacy", "legacy uuid file id must still serve"
c.get(f"/del/{legacy_id}", headers=J, follow_redirects=False)  # logged in by now
assert not os.path.exists(os.path.join("airdrop_files", legacy_id + ".json"))
assert not os.path.exists(os.path.join("airdrop_files", legacy_id + ".txt"))
print("legacy uuid ids still work OK")

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
