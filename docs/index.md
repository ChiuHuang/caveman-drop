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

介面語言由**瀏覽器**決定：每頁內嵌腳本讀 `navigator.languages`（繁中文的
zh-TW／Hant／HK／MO 瀏覽器 → 繁體中文，其他 → English），記在 `lang` cookie
裡，第一次需要換時 reload 一次。`?lang=zh-TW` / `?lang=en` 可手動切換。

登入後是**私人雲端**（跟 Google Drive 一樣）：上傳檔案、點資料夾列進去、
把檔案拖到資料夾列上就移動、從桌面拖進來就直接上傳到那個資料夾。標題旁兩個圖示
是「新增資料夾」與「上傳」，每一列都能改名、分享、刪除，資料夾與檔案在同一個
清單裡一起排序。第二個分頁管理公開檔案（公開資料夾也能改名）。

只給登入用的網域（`PRIVATE_ONLY_HOSTS`，預設 `pvf.chiuhuang.dev`）連這些都
沒有：`/` 未登入就是登入頁，登入後直接是雲端——沒有分頁、沒有公開介面。

原始碼：<https://github.com/ChiuHuang/caveman-drop>

## 接下來去哪

- **快速開始**——60 秒完成第一次上傳。
- **API 參考**——每個端點、方法與回傳格式。
- **限制與規範**——容量上限與頻率限制。
- **自行架設**——安裝、`.env` 設定與反向代理。
- **AI**——抓 `/llms.txt` 或 `/api` 拿機器可讀文件。
