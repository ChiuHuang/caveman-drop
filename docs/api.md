# API 參考

基底網址：伺服器根目錄，例如 `http://localhost:20042`。

連結一律跟著請求走：用 HTTPS 進來就回 HTTPS（讀 `Forwarded` /
`X-Forwarded-Proto`）。想固定網域就設 `PUBLIC_BASE_URL`。

`file_id` 就是檔案內容的 **sha256**：id 相同代表位元組一模一樣。位元組只存
一份（`BIN_DIR`，預設 `bin/`），所以重複上傳不會多佔空間，連結也相同。
回應會帶 `deduplicated: true` 表示這份位元組之前就存過。

## 短網址（CDN 用）

`GET /{code}.{ext}` —— `code` 取 sha256 **最短的唯一前綴**：
一般 6 碼（像 catbox），若另一個檔案前 6 碼相同就自動用 7 碼、8 碼…
回應帶 `Cache-Control: public, max-age=31536000, immutable`，網址永不失效，
可以放心丟給 Cloudflare 快取。每個上傳／清單回應都會附 `short_url`。

只解析公開檔案；私人檔案不會出現在這條路徑（避免被試探）。

```json
{
  "file_id": "f127ca62682b836ac65639814a83d44ce2ff4008209605cb39e444afd6fa2923",
  "short_url": "https://usercontent.qiuhuang.dev/f127ca.pdf",
  "download_url": "https://file.chiuhuang.dev/dl/s/f127ca…"
}
```

內容協商：帶瀏覽器 `User-Agent` + `Accept: text/html` 會拿到 MDUI HTML
控制台；其他一律拿 JSON / 純文字。`?format=json|html|text` 可強制指定。

## 公開（免驗證）

### `POST /api/public/upload`

匿名上傳。Multipart 欄位：`file`（必填）、`folder`（選填）、`description`
（選填）。`folder` 給既有資料夾 id 就加進去，給任意文字就以其為名稱自動開一個
新資料夾。不帶 folder 就是單檔直連，不會建資料夾，回傳 `file_id`、
`filename`、`description`、`size_bytes`、`short_url`、`download_url`、
`file_api_url`；帶 folder 才回傳 `folder_url` 等資料夾欄位。

```bash
curl -F file=@photo.jpg http://localhost:20042/api/public/upload
curl -F file=@photo.jpg -F folder=相簿 http://localhost:20042/api/public/upload
curl -F file=@photo.jpg -F 'description=2026 澎湖行' http://localhost:20042/api/public/upload
```

### `POST /api/public/chunk` → `POST /api/public/merge_chunks`

分段上傳（瀏覽器會自動用）。先並行上傳分塊（multipart：`file_chunk`、
`upload_id`、`index`、`filename`），再 POST JSON（`upload_id`、
`filename`、`total_chunks`、選填 `folder`（id 或名稱）、選填
`description`）合併，回傳與單次上傳相同。

### `POST /api/public/folder/rename`（管理員）

```bash
curl -X POST https://this.host/api/public/folder/rename \
     -H "Content-Type: application/json" \
     -d '{"folder_id":"FOLDER_UUID","name":"new name"}'
```

只改顯示名稱。`folder_id`、分享網址、裡面每個檔案的連結全部照舊可用。

### `POST /api/public/folder`

建立空資料夾（選填 JSON `name`、`perm`）。`perm` 設非擁有者的權限：
`readonly`（只能看＋下載）、`upload`（只能丟檔）、`both`（預設，全開）。
用瀏覽器建立時，資料夾會**綁到這個 session**：建立者不用登入就能
改名（`/api/public/folder/rename`）、改權限（`/api/public/folder/perm`）、
刪除（`/delpubdir/{folder_id}`）。回傳 `folder_id`、`folder_name`、
`folder_url`、`upload_url`、`folder_api_url`。

### `GET /api/public/folder/{folder_id}`

資料夾資訊 + `files[]`，每檔附 `name`、`description`、`download_url`、
`short_url`、`file_api_url`。瀏覽器看到的是資料夾介面。

### `GET /api/public/file/{folder_id}/{file_id}`

單一檔案資訊：`filename`、`description`、`size_bytes`、`content_type`、
`short_url`、`download_url`。
瀏覽器看到的是檔案卡片（含預覽）。

### `GET /dl/pub/{folder_id}/{file_id}`

下載本體。支援 `Range:` 續傳 / 並行抓取。加 `?preview=1` 以 inline
方式回傳，方便瀏覽器預覽。

### 單檔直連（無資料夾）

- `GET /api/public/single/{file_id}`：單檔資訊與直連。
- `GET /dl/s/{file_id}`：下載（`?preview=1` 預覽）。

### `POST /api/public/upload_url`（從網址上傳）

JSON `{"url", "folder"（選填）, "description"（選填）}`：伺服器透過
`PROXY_BASE_URL`（預設 `https://proxy.chiuhuang.dev`）把 URL 抓回來，
bytes 照一般公開上傳入庫（`folder` 規則同上）。匿名呼叫限速
`URL_THROTTLE_MBPS`（預設 60 Mbps）；登入後不限速。回應格式與
`/api/public/upload` 相同。

### 整包下載資料夾（.zip）

- `GET /zip/f/{folder_id}`：公開資料夾整包下成 `.zip`，檔名取資料夾名。
- `GET /zip/{folder_id}`：私人資料夾，需登入。

zip 是**邊打包邊串流**的，伺服器只留一份在記憶體、不寫暫存；無子目錄，
同名檔自動加 ` (1)` 後綴。公開 zip 受資料夾 `perm` 管：`upload`-only 的
資料夾不給打包（403）。

### 私人資料夾分享連結（`/s/{token}`）

- `POST /api/folders/{folder_id}/share`：body `{"mode": "view" | "upload" |
  "both"}`（省略則用建立資料夾時的 `perm`）。回傳 `/s/{token}`。
- `view` = 列出＋下載；`upload` = 匿名投遞箱（不上傳就看不到內容）；
  `both` = 兩者。`POST /api/folders` accepts `perm` 設預設值；改預設值用
  `POST /api/folders/perm`。

## 經代理的客戶端：`?auth=`

CORS 型代理（`https://proxy.example/https://this.host/...`）會轉送請求，但
`Set-Cookie` 回不到瀏覽器，所以 cookie session 在那條路徑上無效。碰到這種
情況，**每個請求**都帶上 `?auth=<PASSWORD>`：

```bash
curl "https://proxy.example/https://this.host/api/files?auth=YOUR_PASSWORD"
curl -F file=@big.iso "https://proxy.example/https://this.host/api/upload_chunk?auth=YOUR_PASSWORD" \
     -F upload_id=... -F index=0 -F filename=big.iso
```

- 只在 **HTTPS** 下生效（明文連線會拒絕）。
- 密碼不會被寫回任何回應或轉址；`/login?auth=...` 會立刻 303 到 `/`，把參數
  丟掉。
- 同一 IP 連續 10 次猜錯就鎖 10 分鐘（回 429）。
- 密碼會出現在網址列／proxy 日誌，請只在受信任的環境使用。

## 私人（密碼 session、`?auth=` 或 `?token=` 手機 token）

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api/files` | 私人檔案清單（JSON；瀏覽器看 HTML） |
| `POST` | `/api/upload_chunk` | 欄位：`file_chunk`、`upload_id`、`index`、`filename` |
| `POST` | `/api/merge_chunks` | JSON：`upload_id`、`filename`、`total_chunks`、選填 `folder_id` |
| `POST` | `/api/folders` | JSON：`name`、選填 `perm`（`view` / `upload` / `both`）—— 新增私人雲端資料夾 |
| `POST` | `/api/folders/rename` | JSON：`folder_id`、`name` —— 改資料夾名字（id、檔案、分享連結都不變） |
| `POST` | `/api/folders/perm` | JSON：`folder_id`、`perm` —— 改分享連結預設權限 |
| `GET` | `/api/folders` | 私人資料夾清單（含檔案數） |
| `GET`/`POST` | `/deldir/{folder_id}` | 刪除私人資料夾（含其中的檔案） |
| `GET` | `/?folder={folder_id}` | 登入後的雲端畫面：資料夾方塊、麵包屑、檔案清單 |
| `POST` | `/api/folders/{id}/share` | JSON：`mode`（`view` 僅檢視 / `upload` 投遞箱 / `both` 都要；省略則用資料夾 `perm`）—— 產生免登入分享連結 |
| `POST` | `/api/share/revoke` | JSON：`token` —— 取消分享 |
| `GET` | `/s/{token}` | 分享資料夾頁（瀏覽器 UI / 純文字） |
| `POST` | `/api/share/merge_chunks` | JSON：`upload_id`、`filename`、`total_chunks`、`token` —— 經分享連結上傳 |
| `GET` | `/dl/sh/{token}/{file_id}` | 分享下載（`?preview=1` 預覽） |
| `GET` | `/dl/{file_id}` | 支援 Range 的私人下載（`?preview=1` 預覽） |
| `GET` | `/view/{file_id}` | 線上預覽 |
| `GET`/`POST` | `/del/{file_id}` | 刪除（`POST` 讓頁面停在原資料夾，不用導走） |
| `POST` | `/api/files/move` | JSON：`file_id`、`folder_id`、`from_folder_id` —— 拖曳移動 |
| `POST` | `/api/public/folder/rename` | JSON：`folder_id`、`name` —— 改公開資料夾名字（網址不變）；建立該資料夾的 session 也可以 |
| `POST` | `/api/public/folder/perm` | JSON：`folder_id`、`perm`（`readonly` / `upload` / `both`）—— 設非擁有者的權限 |
| `POST` | `/api/public/move` | JSON同上 —— 公開檔案拖曳移動 |
| `POST` | `/delpub/{file_id}`、`/delpubdir/{folder_id}` | 從所有公開資料夾移除（管理員或建立者的 session） |
| `GET/POST` | `/m/{token}` | 單檔手機上傳（相容 iPhone 捷徑） |
| `GET/POST` | `/login`、`GET /logout` | 密碼 session |

## 系統

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api` | 完整 JSON 索引（瀏覽器看 HTML 控制台） |
| `GET` | `/llms.txt`、`/api/llms.txt` | 給 AI 的文件，永遠純文字 |
| `GET` | `/docs`、`/docs/{page}` | 圖書館式指南（程式拿 Markdown 原文） |
