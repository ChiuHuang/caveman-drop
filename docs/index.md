# CaveMan Drop

免帳號、純文字優先的檔案分享：給人看的是 Material Design 介面，給腳本與
AI 看的是純 JSON / 純文字 API。

## 運作方式

1. **上傳**檔案——免帳號：
   `POST /api/public/upload`，multipart 欄位叫 `file`。
2. 拿回**下載連結**（`/dl/pub/…`）與**資料夾連結**（`/f/…`）。
3. 分享資料夾連結。知道的人可下載，也可用同一個端點加 `folder` 欄位
   把更多檔案加入同一個資料夾。

瀏覽器自動看到 MDUI 網頁介面；`curl`、Python、AI 拿到 JSON 或純文字。
用 `?format=html` / `?format=json` 可強制切換。

登入後進入私人模式：分段上傳、私人檔案清單、預覽、下載、
直接連結與刪除。

原始碼：<https://github.com/ChiuHuang/caveman-drop>

## 接下來去哪

- **快速開始**——60 秒完成第一次上傳。
- **API 參考**——每個端點、方法與回傳格式。
- **限制與規範**——容量上限與頻率限制。
- **AI**——抓 `/llms.txt` 或 `/api` 拿機器可讀文件。
