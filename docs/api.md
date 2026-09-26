# API 參考

基底網址：伺服器根目錄，例如 `http://localhost:20042`。

內容協商：帶瀏覽器 `User-Agent` + `Accept: text/html` 會拿到 MDUI HTML
控制台；其他一律拿 JSON / 純文字。`?format=json|html|text` 可強制指定。

## 公開（免驗證）

### `POST /api/public/upload`

匿名上傳。Multipart 欄位：`file`（必填）、`folder`（選填，既有資料夾
id）。回傳 `folder_id`、`file_id`、`filename`、`size_bytes`、
`content_type`、`url`、`download_url`、`folder_url`、`share_url`、
`folder_api_url`、`file_api_url`。

### `POST /api/public/folder`

建立空資料夾。回傳 `folder_id`、`folder_url`、`upload_url`、
`folder_api_url`。

### `GET /api/public/folder/{folder_id}`

資料夾資訊 + `files[]`，每檔附 `download_url` / `file_api_url`。
瀏覽器看到的是資料夾介面。

### `GET /api/public/file/{folder_id}/{file_id}`

單一檔案資訊：`filename`、`size_bytes`、`content_type`、`download_url`。
瀏覽器看到的是檔案卡片（含預覽）。

### `GET /dl/pub/{folder_id}/{file_id}`

下載本體。支援 `Range:` 續傳 / 並行抓取。加 `?preview=1` 以 inline
方式回傳，方便瀏覽器預覽。

## 私人（密碼 session 或 `?token=` 手機 token）

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/api/files` | 私人檔案清單（JSON；瀏覽器看 HTML） |
| `POST` | `/api/upload_chunk` | 欄位：`file_chunk`、`upload_id`、`index`、`filename`（前端以 16 線程並行） |
| `POST` | `/api/merge_chunks` | JSON：`upload_id`、`filename`、`total_chunks` |
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
