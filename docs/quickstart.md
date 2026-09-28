# 快速開始

## 上傳（單檔直連，不建資料夾）

```bash
curl -F file=@photo.jpg http://localhost:20042/api/public/upload
```

回傳（JSON）：直接給下載連結，不會建資料夾。`file_id` 是內容的 sha256。

```json
{
  "success": true,
  "file_id": "…64 碼 sha256…",
  "deduplicated": false,
  "download_url": "http://localhost:20042/dl/s/…"
}
```

同一個檔案再傳一次：`file_id` 與連結完全相同，`deduplicated` 為 `true`，
伺服器只留一份位元組（`bin/`），不會存兩次。

## 建資料夾、合傳

網頁切到「建立資料夾」分頁填個名字建好後，把資料夾連結分享給別人；
對方在資料夾頁上傳就會加進同一包。程式用：

```bash
curl -X POST http://localhost:20042/api/public/folder -H 'Content-Type: application/json' -d '{"name":"相簿"}'
curl -F file=@notes.txt -F folder=FOLDER_ID http://localhost:20042/api/public/upload
```

`folder` 欄位很寬鬆：給 id 就是加進那個資料夾，給任何文字就直接開一個以它
為名字的新資料夾並上傳進去。網頁上傳表單的「資料夾」欄位也是同一套規則
（留空＝單檔直連）。

## HTTPS 連結

回傳的網址會跟著請求走：訪客用 HTTPS 進來就給 HTTPS 連結
（讀 `Forwarded` / `X-Forwarded-Proto`）。反向代理沒帶這些標頭時，
設 `.env` 的 `PUBLIC_BASE_URL=https://file.example.com` 強制指定。

## 用 Python 上傳

```python
import httpx

with open("photo.jpg", "rb") as f:
    r = httpx.post("http://localhost:20042/api/public/upload", files={"file": f})
print(r.json()["download_url"])
```

## 用瀏覽器上傳

打開 `/upload`，選檔後自動分段上傳，下方有即時監控面板：
總進度、速度（依實際經過時間計算，並顯示全程平均）、分段格與線程狀態，
可暫停。上傳完直接顯示下載連結、資料夾連結與平均速度。

## 大檔案：分段上傳（程式用）

```python
import httpx, uuid, math

BASE = "http://localhost:20042"
uid = str(uuid.uuid4())
data = open("big.bin", "rb").read()
CS, total = 4 * 1024 * 1024, math.ceil(len(data) / (4 * 1024 * 1024))
for i in range(total):
    httpx.post(f"{BASE}/api/public/chunk", files={"file_chunk": data[i*CS:(i+1)*CS]},
               data={"upload_id": uid, "index": str(i), "filename": "big.bin"})
r = httpx.post(f"{BASE}/api/public/merge_chunks",
               json={"upload_id": uid, "filename": "big.bin", "total_chunks": total})
print(r.json()["download_url"])

上傳前可先 POST 2MB 到 `/api/public/probe` 測速，回傳適合的並行數
（慢連線會自動加到 32 / 64 / 128），瀏覽器會自動做這件事。瀏覽器用自己
的碼表量整個來回時間（含 DNS/TCP/TLS），所以量到的就是真實上傳速度。
```

## 私人模式

打開 `/login` 輸入伺服器 `PASSWORD`：分段上傳、私人檔案清單
（`/api/files`）、線上預覽（`/view/<id>`）、下載與刪除。
登入後介面只顯示私人空間，不受分享頻寬限速影響。
