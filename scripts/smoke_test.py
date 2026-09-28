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
assert "API index" in r.text
print("browser /api OK")

r = c.get("/llms.txt", headers=J)
assert r.text.startswith("# CaveMan Drop")
print("llms OK")

r = c.get("/upload", headers=B)
assert "data-chunked" in r.text and "data-tp-segs" in r.text
assert "Up to 5 GB per file" in r.text and "throttled past that" in r.text
assert "Create folder" in r.text and "data-tabs" in r.text
assert "Description (optional)" in r.text
print("browser /upload OK (thread panel present)")

r = c.get("/docs", headers=B)
assert "docs-layout" in r.text
print("browser /docs OK")
r = c.get("/docs/api", headers=J)
assert r.text.startswith("# API 參考")
print("curl /docs/api OK")

# --- legal page: bilingual, Taiwan law, reachable at /legal ---
lg = c.get("/docs/legal", headers=J)
assert lg.text.startswith("# 法律條款 / Legal"), lg.text[:40]
for cite in ("第六章之一", "民事免責事由實施辦法", "兒童及少年性剝削防制條例",
             "刑法", "個人資料保護法", "通信秘密保障法", "24 小時內", "7 個工作天",
             "319 條之 3", "第 38 條"):
    assert cite in lg.text, f"missing Taiwan-law citation: {cite}"
assert "中華民國" in lg.text and "Republic of China (Taiwan)" in lg.text
assert "臺灣沒有美國 DMCA" in lg.text, "must state that the DMCA regime does not apply here"
for absent in ("Digital Millennium", "mainland", "中華人民共和國", "PRC", "Cybersecurity Law",
               "PIPL", "censor"):
    assert absent not in lg.text, f"wrong-jurisdiction text leaked in: {absent}"
lgb = c.get("/docs/legal", headers=B)
assert "docs-layout" in lgb.text and "Legal" in lgb.text
r = c.get("/legal", headers=B, follow_redirects=False)
assert r.status_code == 303 and r.headers["location"] == "/docs/legal"
h = c.get("/", headers=B).text
assert 'class="legalbar"' in h
assert h.index("legalbar") > h.index("Public upload"), "legal must be at the bottom"
assert "data-tos" not in h
print("legal page OK (zh-TW + English, Taiwan law, bottom of page)")

# --- ?auth=<PASSWORD> for proxied clients that cannot carry our cookie ---
import app.auth as _auth

anon2 = TestClient(app)                       # never logged in, no cookie
H = {**J, "X-Forwarded-Proto": "https", "CF-Connecting-IP": "203.0.113.11"}
HB = {**B, "X-Forwarded-Proto": "https", "CF-Connecting-IP": "203.0.113.11"}
assert "data-drive" in anon2.get("/?auth=passw", headers=HB).text, "?auth= must open the drive"
assert "data-drive" not in anon2.get("/?auth=passw", headers=B).text, "plain http must not take ?auth="
assert "data-drive" not in anon2.get("/?auth=wrong", headers=HB).text
r = anon2.get("/login?auth=passw", headers=HB, follow_redirects=False)
assert r.status_code == 303 and r.headers["location"] == "/", "secret must be stripped on redirect"
assert "passw" not in anon2.get("/?auth=passw", headers=HB).text, "password must never be echoed"
assert anon2.get("/api/files?auth=passw", headers=H).status_code == 200
anon2.cookies.clear()   # GET /login?auth= above may have set one; the param must work alone
assert anon2.get("/api/files", headers=H).status_code == 401, "no cookie, no param"
mf2 = anon2.post("/api/folders?auth=passw", headers=H, json={"name": "param folder"})
assert mf2.status_code == 200 and mf2.json()["name"] == "param folder"
# chunked private upload with only the param
_auth._fails.clear()
u2 = str(uuid.uuid4())
anon2.post("/api/upload_chunk?auth=passw", headers=H, files={"file_chunk": ("c", b"param bytes")},
           data={"upload_id": u2, "index": "0", "filename": "pp.txt"})
m2 = anon2.post("/api/merge_chunks?auth=passw", headers=H,
                json={"upload_id": u2, "filename": "pp.txt", "total_chunks": 1})
assert m2.json()["success"]
assert anon2.get(f"/dl/{m2.json()['file_id']}", headers=H).content == b"param bytes"
# brute force is throttled on HTML pages, and the budget is per IP
_auth._fails.clear()
codes = [anon2.get("/?auth=nope", headers=HB).status_code for _ in range(12)]
assert 429 in codes, codes
_auth._fails.clear()
assert "data-drive" in anon2.get("/?auth=passw", headers=HB).text, "another IP is unaffected"
print("?auth= param (proxy case) OK")

# --- language follows the client IP: zh-TW for Taiwan ranges, English elsewhere ---
TW = {**B, "CF-Connecting-IP": "120.122.9.9"}
EN_IP = {**B, "CF-Connecting-IP": "8.8.8.8"}
zh = c.get("/", headers=TW).text
en = c.get("/", headers=EN_IP).text
assert 'lang="zh-TW"' in zh
assert "免帳號的匿名檔案分享" in zh and "首頁" in zh and "公開上傳" in zh
assert 'lang="en"' in en
assert "Anonymous file sharing" in en and "Home" in en and "Public upload" in en
assert "首頁" not in en and "免帳號" not in en, "non-Taiwan IP must not get Chinese"
# ?lang override wins over the IP
assert "免帳號" in c.get("/?lang=zh-TW", headers=EN_IP).text
assert "Anonymous file sharing" in c.get("/?lang=en", headers=TW).text
# the footer offers the other language
assert 'href="?lang=en"' in c.get("/", headers=TW).text and 'href="?lang=zh-TW"' in c.get("/", headers=EN_IP).text
# every page renders in both languages
for path in ("/", "/upload", "/login", "/api", "/docs", "/legal"):
    a = c.get(path, headers=TW)
    b = c.get(path, headers=EN_IP)
    assert a.status_code == b.status_code == 200, (path, a.status_code, b.status_code)
    assert 'lang="zh-TW"' in a.text, f"{path} should be zh-TW for a Taiwan IP"
    assert 'lang="en"' in b.text, f"{path} should be English for a non-Taiwan IP"
zh_up = c.get("/upload", headers=TW).text
en_up = c.get("/upload", headers=EN_IP).text
assert "建立資料夾" in zh_up and "Create folder" in en_up
assert "說明（選填）" in zh_up and "Description (optional)" in en_up
assert "單檔上限 5 GB" in zh_up and "Up to 5 GB per file" in en_up
# admin pages too
adm = TestClient(app)
adm.post("/login", data={"password": "passw"})
zh_adm = adm.get("/", headers=TW).text
en_adm = adm.get("/", headers=EN_IP).text
assert "我的雲端" in zh_adm and "My drive" in en_adm
assert "公開（" in zh_adm and "Public (" in en_adm
# Taiwan range boundaries from the brief
for ip in ("1.32.208.0", "1.32.215.255", "36.224.0.0", "36.239.255.255", "120.120.0.0",
           "120.121.5.5", "120.123.255.255", "220.135.0.0", "220.135.255.255"):
    assert 'lang="zh-TW"' in c.get("/", headers={**B, "CF-Connecting-IP": ip}).text, ip
for ip in ("1.32.207.255", "1.32.216.0", "36.223.255.255", "36.240.0.0", "120.119.255.255",
           "120.124.0.0", "220.134.255.255", "220.136.0.0", "1.1.1.1"):
    assert 'lang="en"' in c.get("/", headers={**B, "CF-Connecting-IP": ip}).text, ip
print("language by client IP OK (zh-TW ranges vs English elsewhere)")

# --- no probe request from the browser: it adapts from the first chunks ---
r = c.get("/upload", headers=B)
assert "data-probe" not in r.text, "browser must not fire a separate probe"
assert 'data-chunked' in r.text
js = open("app/static/app.js", encoding="utf-8").read()
assert "ADAPT_CHUNKS" in js and "probeThroughput" not in js
assert "xhr.upload.onprogress" in js, "upload speed must come from real progress events"
print("first-chunk speed adaptation OK (no probe request)")

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

# --- short share code: /usercontent/<shortest unique prefix>.<ext> ---
from app.storage import short_code, resolve_short_code, MIN_CODE
code = short_code(fid)
assert code == fid[:MIN_CODE] and len(code) == 6, code
assert resolve_short_code(code) == fid
uc = c.get(f"/usercontent/{code}.txt", headers=J)
assert uc.status_code == 200 and uc.content == b"hi caveman", uc.status_code
assert "attachment" in uc.headers["content-disposition"]
assert uc.headers["cache-control"] == "public, max-age=31536000, immutable"
ucr = c.get(f"/usercontent/{code}", headers={**J, "Range": "bytes=2-5"})
assert ucr.status_code == 206 and ucr.content == b"hi caveman"[2:6], (ucr.status_code, ucr.content)
assert c.get("/usercontent/ffffff", headers=J).status_code == 404
assert c.get("/usercontent/zz", headers=J).status_code == 404
assert c.get(f"/usercontent/{fid}", headers=J).content == b"hi caveman"  # full id works too
# a 6-char clash between two different files pushes the newcomer to 7 chars
fake = {"codes": {}, "hashes": {}}
import app.storage as _st2
real_load, real_save = _st2._load_index, _st2._save_index
try:
    _st2._load_index = lambda: {"codes": dict(fake["codes"]), "hashes": dict(fake["hashes"])}
    _st2._save_index = lambda idx: fake.update(codes=dict(idx["codes"]), hashes=dict(idx["hashes"]))
    h1 = "abcdef" + "1" * 58
    h2 = "abcdef" + "2" * 58
    assert short_code(h1) == "abcdef"
    assert short_code(h2) == "abcdef2", "clashing prefix must grow to 7 chars"
    assert resolve_short_code("abcdef2") == h2
    # and a third file whose 7 chars also clash grows again
    h3 = "abcdef2" + "3" * 57
    assert short_code(h3) == "abcdef23"
finally:
    _st2._load_index, _st2._save_index = real_load, real_save
print("short codes OK (6 chars, grows on clash)")

# --- custom description via the API ---
desc_up = c.post("/api/public/upload", headers=J,
                 files={"file": ("note.txt", b"described bytes")},
                 data={"description": "週會記錄 2026-09-28"})
assert desc_up.json()["description"] == "週會記錄 2026-09-28", desc_up.json()
dfid = desc_up.json()["file_id"]
dm = c.get(f"/api/public/single/{dfid}", headers=J)
assert dm.json()["description"] == "週會記錄 2026-09-28"
dshort = dm.json()["short_url"]
assert dshort.endswith(".txt") and "/usercontent/" in dshort, dshort
assert c.get(dshort.replace("http://testserver", ""), headers=J).content == b"described bytes"
# control characters stripped, long text capped
d2 = c.post("/api/public/upload", headers=J, files={"file": ("n2.txt", b"two")},
            data={"description": "bad\x00chars" + "x" * 400})
assert "\x00" not in d2.json()["description"] and len(d2.json()["description"]) <= 200
hm = c.get("/upload", headers=B)
assert 'name="description"' in hm.text
print("custom description OK")

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
print("folder json+html OK")

d = c.get(f"/dl/pub/{folder}/{jfid}", headers=J)
assert d.status_code == 200 and d.content == b"joined"
print("folder download OK")

h = c.get(f"/f/{folder}", headers=B)
assert "Public folder" in h.text and "Add files to this folder" in h.text
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
# 95 Mbps real throughput must land on 16 threads, not 64
assert threads_for_speed(95 * 1_000_000 / 8) == 16, "95 Mbps should be 16 threads"
assert threads_for_speed(40 * 1_000_000 / 8) == 32
assert threads_for_speed(16 * 1_000_000 / 8) == 64
assert threads_for_speed(8 * 1_000_000 / 8) == 128
print("probe + IP tag OK")

# --- login -> private mode, public upload hidden ---
# Push the test IP over budget first: private session must stay exempt.
_st.bw_record("testclient", None, 200 * 1024 * 1024)
r = c.post("/login", headers=J, data={"password": "passw"})
assert r.status_code == 200
print("login OK")

r = c.get("/", headers=B)
assert "My drive" in r.text and "data-chunked" in r.text
assert "data-drive" in r.text
# Drive layout: breadcrumb, folder tiles, drop targets, new-folder + upload icons
assert 'class="crumb"' in r.text and "data-new-folder" in r.text and "data-drive-upload" in r.text
assert 'data-dropscope="private"' in r.text and "data-dropscope=\"public\"" in r.text
# two tabs only: the drive and the public area
assert 'value="drive"' in r.text and 'value="public"' in r.text
assert 'value="all"' not in r.text and 'value="folders"' not in r.text, "no more tab soup"
assert 'class="legalbar"' in r.text and '/legal' in r.text, "legal link at the bottom"
print("private-mode dashboard OK (drive: tiles, breadcrumb, drop targets)")

r = c.get("/upload", headers=B, follow_redirects=False)
assert r.status_code == 303, "logged-in /upload should redirect to /"
print("logged-in /upload redirect OK")

h = c.get(f"/f/{folder}", headers=B)
assert "data-chunked" not in h.text, "no upload form on the public folder page when signed in"
assert "Sign out to upload" in h.text
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
assert "big.bin" in r.text and "Direct link" in r.text and "Delete" in r.text and "Preview" in r.text
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
assert "工作" in r.text and "data-delete-dir" in r.text and "My drive" in r.text
assert "data-rename" in r.text, "folders can be renamed from the drive"
assert 'data-dropfolder="%s"' % pfolder in r.text, "folder tile must be a drop target"
assert 'data-dropscope="private"' in r.text and 'data-move=' in r.text
assert "draggable=\"true\"" in r.text, "file rows must be draggable"
# opening the folder lists its files and keeps the breadcrumb
r = c.get(f"/?folder={pfolder}", headers=B)
assert "w.txt" in r.text and "工作" in r.text, "folder view lists its files"
assert f'href="/?folder={pfolder}"' not in r.text, "no self-link on the open folder tile"
assert 'name="folder_id" value="%s"' % pfolder in r.text, "uploader targets the open folder"
assert f'href="?folder={pfolder}&amp;lang=zh-TW"' in r.text, "language switch keeps the folder"
# renaming from the API keeps the id and the files
rn = c.post("/api/folders/rename", headers=J, json={"folder_id": pfolder, "name": "工作 renamed"})
assert rn.status_code == 200 and rn.json()["name"] == "工作 renamed"
assert any(x["id"] == pfolder and x["count"] == 1 for x in c.get("/api/folders", headers=J).json()["folders"])
assert "工作 renamed" in c.get(f"/?folder={pfolder}", headers=B).text
assert c.post("/api/folders/rename", headers=J, json={"folder_id": "nope", "name": "x"}).status_code == 404
rn = c.post("/api/folders/rename", headers=J, json={"folder_id": pfolder, "name": "工作"})
assert rn.json()["name"] == "工作"
# a public folder can be renamed too, and its URL still works
assert c.post("/api/public/folder/rename", headers=J,
              json={"folder_id": folder, "name": "renamed public"}).json()["name"] == "renamed public"
assert "renamed public" in c.get(f"/f/{folder}", headers=B).text
assert c.post("/api/public/folder/rename", headers=J,
              json={"folder_id": str(uuid.uuid4()), "name": "x"}).status_code == 404
# renaming needs auth
assert anon2.post("/api/folders/rename", headers=J,
                  json={"folder_id": pfolder, "name": "x"}).status_code == 401
assert anon2.post("/api/public/folder/rename", headers=J,
                  json={"folder_id": folder, "name": "x"}).status_code == 401
print("drive folders: rename + open + drop targets OK")

# --- rename a file: display name only, id and bytes stay ---
rf = c.post("/api/files/rename", headers=J, json={"file_id": wfid, "name": "renamed.txt"})
assert rf.status_code == 200 and rf.json()["name"] == "renamed.txt"
assert c.get(f"/dl/{wfid}", headers=J).content == b"data", "bytes must survive a rename"
assert "renamed.txt" in c.get(f"/?folder={pfolder}", headers=B).text
assert c.get("/api/files", headers=J).json()["files"][0]["id"] == wfid
assert c.post("/api/files/rename", headers=J, json={"file_id": "nope", "name": "x"}).status_code == 404
# public file rename, located by its folder
pfile = c.get(f"/api/public/folder/{folder}", headers=J).json()["files"][0]
rf = c.post("/api/public/file/rename", headers=J,
            json={"file_id": pfile["id"], "name": "pub renamed.bin", "folder_id": folder})
assert rf.status_code == 200 and rf.json()["name"] == "pub renamed.bin"
pubmeta = c.get(f"/api/public/file/{folder}/{pfile['id']}", headers=J).json()
assert pubmeta["filename"] == "pub renamed.bin" and pubmeta["file_id"] == pfile["id"]
assert c.get(f"/dl/pub/{folder}/{pfile['id']}", headers=J).status_code == 200
assert c.post("/api/public/file/rename", headers=J,
              json={"file_id": "nope", "name": "x"}).status_code == 404
# the drive offers a rename button on file rows too
assert 'data-rename-file="%s"' % wfid in c.get(f"/?folder={pfolder}", headers=B).text
assert 'data-rename-file="%s"' % pfile["id"] in c.get("/", headers=B).text
print("rename files OK (display name only)")

# --- share folder: view-only vs upload ---
sv = c.post(f"/api/folders/{pfolder}/share", headers=J, json={"mode": "view"})
assert sv.status_code == 200
vtok = sv.json()["token"]
su = c.post(f"/api/folders/{pfolder}/share", headers=J, json={"mode": "upload"})
utok = su.json()["token"]
assert su.json()["url"].endswith(f"/s/{utok}")

sp = c.get(f"/s/{vtok}", headers=B)
assert "工作" in sp.text and "renamed.txt" in sp.text and "View only" in sp.text
assert "Upload to this folder" not in sp.text
sp = c.get(f"/s/{utok}", headers=B)
assert "Can upload" in sp.text and "Upload to this folder" in sp.text
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

# --- admin sees everything: /api/public/files lists singles + folder files ---
allpub = c.get("/api/public/files", headers=J)
assert allpub.status_code == 200, allpub.text
names = {f["name"] for f in allpub.json()["files"]}
assert {"hello.txt", "pub renamed.bin"} <= names, names
assert any(f["name"] == "派對" for f in allpub.json()["folders"])
anon = TestClient(app)                    # no session cookie: must be refused
r = anon.get("/api/public/files", headers=B)
assert r.status_code in (401, 303), r.status_code
assert anon.post("/api/public/move", json={"file_id": "x", "folder_id": None}).status_code == 401
assert anon.post(f"/delpub/{fid}").status_code == 401
print("admin file list OK")

# --- drag and drop: move a public file into a public folder, and out again ---
pub_fid = f.json()["file_id"]          # hello.txt, folderless
target = c.post("/api/public/folder", headers=J, json={"name": "拖放目標"}).json()["folder_id"]
mv = c.post("/api/public/move", headers=J,
            json={"file_id": pub_fid, "folder_id": target, "from_folder_id": ""})
assert mv.status_code == 200 and mv.json()["folder_id"] == target, mv.text
assert c.get(f"/dl/pub/{target}/{pub_fid}", headers=J).content == b"hi caveman"
assert any(f["id"] == pub_fid for f in c.get(f"/api/public/folder/{target}", headers=J).json()["files"])
back = c.post("/api/public/move", headers=J,
              json={"file_id": pub_fid, "folder_id": None, "from_folder_id": target})
assert back.status_code == 200 and back.json()["folder_id"] == ""
assert c.get(f"/dl/s/{pub_fid}", headers=J).content == b"hi caveman"
print("public drag-move OK")

# private move + admin deletes of public entries
pv = c.post("/api/files/move", headers=J, json={"file_id": priv_id, "folder_id": None})
assert pv.status_code == 200
assert c.post("/api/public/move", headers=J, json={"file_id": priv_id, "folder_id": target}).status_code == 404
dp = c.post(f"/delpub/{jfid}", headers=J)
assert dp.status_code == 200 and dp.json()["deleted"] >= 1
assert c.get(f"/dl/pub/{folder}/{jfid}", headers=J).status_code == 404
dd = c.post(f"/delpubdir/{target}", headers=J)
assert dd.status_code == 200
assert c.get(f"/f/{target}", headers={**B}).status_code == 404
assert c.post("/delpub/does-not-exist", headers=J).status_code == 404
print("admin public delete OK")

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
