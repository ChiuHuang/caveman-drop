# API 參考

基底網址：伺服器根目錄，例如 `http://localhost:20042`。

內容協商：帶瀏覽器 `User-Agent` + `Accept: text/html` 會拿到 MDUI HTML
控制台；其他一律拿 JSON / 純文字。`?format=json|html|text` 可強制指定。

## 公開（免驗證）

### `POST /api/public/upload`

匿名上傳。Multipart 欄位：`file`（必填）、`folder`（選填，既有資料夾
id）。不帶 folder 就是單檔直連，不會建資料夾，回傳 `file_id`、`filename`、
`size_bytes`、`download_url`、`file_api_url`；帶 folder 才回傳
`folder_url` 等資料夾欄位。

### `POST /api/public/chunk` → `POST /api/public/merge_chunks`

分段上傳（瀏覽器會自動用）。先並行上傳分塊（multipart：`file_chunk`、
`upload_id`、`index`、`filename`），再 POST JSON（`upload_id`、
`filename`、`total_chunks`、選填 `folder`）合併，回傳與單次上傳相同。

### `POST /api/public/folder`

建立空資料夾（選填 JSON `name`）。回傳 `folder_id`、`folder_name`、
`folder_url`、`upload_url`、`folder_api_url`。

### `GET /api/public/folder/{folder_id}`

資料夾資訊 + `files[]`，每檔附 `download_url` / `file_api_url`。
瀏覽器看到的是資料夾介面。

### `GET /api/public/file/{folder_id}/{file_id}`

單一檔案資訊：`filename`、`size_bytes`、`content_type`、`download_url`。
瀏覽器看到的是檔案卡片（含預覽）。

### `GET /dl/pub/{folder_id}/{file_id}`

下載本體。支援 `Range:` 續傳 / 並行抓取。加 `?preview=1` 以 inline
方式回傳，方便瀏覽器預覽。

### 單檔直連（無資料夾）

- `GET /api/public/single/{file_id}`：單檔資訊與直連。
- `GET /dl/s/{file_id}`：下載（`?preview=1` 預覽）。

## 私人（密碼 session 或 `?token=` 手機 token）

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api/files` | 私人檔案清單（JSON；瀏覽器看 HTML） |
| `POST` | `/api/upload_chunk` | 欄位：`file_chunk`、`upload_id`、`index`、`filename` |
| `POST` | `/api/merge_chunks` | JSON：`upload_id`、`filename`、`total_chunks`、選填 `folder_id` |
| `POST` | `/api/folders` | JSON：`name` —— 新增私人雲端資料夾 |
| `GET` | `/api/folders` | 私人資料夾清單（含檔案數） |
| `GET` | `/deldir/{folder_id}` | 刪除私人資料夾（含其中的檔案） |
| `POST` | `/api/folders/{id}/share` | JSON：`mode`（`view` 僅檢視 / `upload` 可上傳）—— 產生免登入分享連結 |
| `POST` | `/api/share/revoke` | JSON：`token` —— 取消分享 |
| `GET` | `/s/{token}` | 分享資料夾頁（瀏覽器 UI / 純文字） |
| `POST` | `/api/share/merge_chunks` | JSON：`upload_id`、`filename`、`total_chunks`、`token` —— 經分享連結上傳 |
| `GET` | `/dl/sh/{token}/{file_id}` | 分享下載（`?preview=1` 預覽） |
| `GET` | `/dl/{file_id}` | 支援 Range 的私人下載（`?preview=1` 預覽） |
| `GET` | `/view/{file_id}` | 線上預覽 |
| `GET` | `/del/{file_id}` | 刪除（瀏覽器會先跳確認再導回首頁） |
| `GET/POST` | `/m/{token}` | 單檔手機上傳（相容 iPhone 捷徑） |
| `GET/POST` | `/login`、`GET /logout` | 密碼 session |

## 系統

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api` | 完整 JSON 索引（瀏覽器看 HTML 控制台） |
| `GET` | `/llms.txt`、`/api/llms.txt` | 給 AI 的文件，永遠純文字 |
| `GET` | `/docs`、`/docs/{page}` | 圖書館式指南（程式拿 Markdown 原文） |
