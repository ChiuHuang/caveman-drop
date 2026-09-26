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

打開 `/upload`，選檔後複製連結即可——瀏覽器 JS 也可直接 `fetch` +
`FormData` 打同一個端點（CORS 已開放）。

## 私人模式

打開 `/login` 輸入伺服器 `PASSWORD`：16 線程分段上傳、私人檔案清單
（`/api/files`）、線上預覽（`/view/<id>`）、16 線程下載與刪除。
登入後介面只顯示私人空間，不再顯示公開上傳。
