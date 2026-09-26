# 快速開始

## 用 curl 上傳

```bash
# 一次建好分享資料夾並上傳檔案
curl -F file=@photo.jpg http://localhost:20042/api/public/upload
```

回傳（JSON）：

```json
{
  "success": true,
  "folder_id": "…",
  "file_id": "…",
  "download_url": "http://localhost:20042/dl/pub/…/…",
  "folder_url": "http://localhost:20042/f/…"
}
```

## 加入現有資料夾

```bash
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

打開 `/upload`，選檔後即以 16 線程分段上傳，下方有 IDM 式監控面板：
總進度條、速度、分段格（藍色=完成）與 16 條線程即時狀態，可暫停。
上傳完直接顯示下載連結——瀏覽器 JS 也可直接 `fetch` 打同一個端點
（CORS 已開放）。

## 大檔案：16 線程分段上傳（程式用）

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
```

## 私人模式

打開 `/login` 輸入伺服器 `PASSWORD`：16 線程分段上傳、私人檔案清單
（`/api/files`）、線上預覽（`/view/<id>`）、16 線程下載與刪除。
登入後介面只顯示私人空間，不再顯示公開上傳。
