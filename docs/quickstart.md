# 快速開始

## 上傳（單檔直連，不建資料夾）

```bash
curl -F file=@photo.jpg http://localhost:20042/api/public/upload
```

回傳（JSON）：直接給下載連結，不會建資料夾。

```json
{
  "success": true,
  "file_id": "…",
  "download_url": "http://localhost:20042/dl/s/…"
}
```

## 建資料夾、合傳

網頁切到「建立資料夾」分頁建好後，把資料夾連結分享給別人；
對方在資料夾頁上傳就會加進同一包。程式用：

```bash
curl -X POST http://localhost:20042/api/public/folder
curl -F file=@notes.txt -F folder=FOLDER_ID http://localhost:20042/api/public/upload
```

## 用 Python 上傳

```python
import httpx

with open("photo.jpg", "rb") as f:
    r = httpx.post("http://localhost:20042/api/public/upload", files={"file": f})
print(r.json()["download_url"])
```

## 用瀏覽器上傳

打開 `/upload`，選檔後自動分段上傳，下方有即時監控面板：
總進度、速度、分段格與線程狀態，可暫停。上傳完直接顯示下載連結。

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

上傳前可先 POST 1MB 到 `/api/public/probe` 測速，回傳適合的並行數
（慢連線會自動加到 32 / 64 / 128），瀏覽器會自動做這件事。
```

## 私人模式

打開 `/login` 輸入伺服器 `PASSWORD`：分段上傳、私人檔案清單
（`/api/files`）、線上預覽（`/view/<id>`）、下載與刪除。
登入後介面只顯示私人空間，不受分享頻寬限速影響。
