# CaveMan Drop

原始碼：<https://github.com/ChiuHuang/caveman-drop>

免帳號、純文字優先的檔案分享。從任何腳本、瀏覽器或 AI 上傳檔案——立刻拿回永久連結。公開分享不需要帳號。

- **瀏覽器**在每個頁面與端點都看到 Material Design 3 介面（MDUI v2）。
- **語言**跟著來源 IP：台灣網段（1.32.208.0/21、36.224.0.0/12、120.120–120.123、
  220.135.0.0/16）給繁體中文，其他 IP 給 English。`?lang=zh-TW` / `?lang=en`
  可覆寫（見 `app/i18n.py`）。
- **腳本與 AI**（`curl`、Python、AI 工具）透過內容協商拿到純 JSON / 純文字。加上 `?format=json` 或 `?format=html` 可強制指定。
- 機器可讀文件在 `/llms.txt`；完整 API 索引在 `/api`。
- 登入後進入**私人模式**：只有私人空間，不再顯示公開上傳。

## 快速開始

```bash
# 1. 設定
cp .env.example .env   # 然後設定 PASSWORD

# 2. 安裝 + 執行（Linux 伺服器用 deploy.sh 全自動）
uv venv
uv pip install fastapi "uvicorn[standard]" python-dotenv python-multipart itsdangerous markdown httpx
uv run main.py
# 或：uv run uvicorn main:app --host 0.0.0.0 --port 20042
# 或（正式環境）：python -m gunicorn app:app -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:20042
```

上傳第一個檔案：

```bash
curl -F file=@photo.jpg http://localhost:20042/api/public/upload
```

## 目錄結構

```
main.py              # 進入點（uvicorn）
deploy.sh            # 伺服器開機 / 自動更新腳本（POSIX sh）
requirements.txt     # pip 部署用依賴（含 gunicorn）
app/
  __init__.py        # FastAPI 工廠、中介層、錯誤頁
  config.py          # .env 設定（連接埠、密碼、限制、目錄）
  negotiation.py     # 瀏覽器 vs 程式的內容協商
  i18n.py            # 依來源 IP 選語言（台灣網段中文、其他英文）＋字串表
  auth.py            # session cookie 或 ?auth=<PASSWORD>（給走代理的客戶端）
  storage.py         # 檔案儲存、配額、速率限制、下載、sha256 bin
  urls.py            # 反向代理後仍正確的基底網址（https 進 → https 出）
  ui.py              # 全站共用 MDUI v2 繁中 HTML 外殼
  static/            # app.css + app.js（/static 提供）
  routes/
    pages.py         # /、/login、/logout、/upload、/f/{folder}
    public_api.py    # POST /api/public/upload|folder、查詢、/dl/pub/…
    private_api.py   # 密碼 + 手機 token、私人分段上傳、/dl、/view、/del
    system.py        # /api 索引、/llms.txt
    docs.py          # 圖書館式 /docs，內容來自 docs/*.md
docs/                # /docs 的 Markdown 來源（GitHub 上也可直接閱讀）
```

## 設定

見 `.env.example`。重要變數：

| 變數 | 預設 | 用途 |
|---|---|---|
| `PORT`（`SERVER_PORT` 也可） | `20042` | 監聽連接埠 |
| `PUBLIC_BASE_URL` | 空 | 產生連結時的固定基底網址；留空＝跟著請求走 |
| `PASSWORD` | `passw` | 私人後台密碼——**務必修改** |
| `SECRET_KEY` | 自動產生 | Session 簽名（存於 `.secret_key`） |
| `UPLOAD_DIR` / `TMP_DIR` / `PUBLIC_DIR` | `airdrop_files` / `airdrop_tmp` / `public_uploads` | 儲存目錄 |
| `BIN_DIR` | `bin` | sha256 位元組庫（同一份內容只存一次） |
| `MAX_FILE_SIZE_GB` | `5` | 公開單檔上限（登入後無上限） |
| `RATE_LIMIT_MAX_UPLOADS` / `RATE_LIMIT_WINDOW_SECONDS` | `30` / `3600` | 單 IP 上傳頻率限制 |
| `BW_WINDOW_SECONDS` | `600` | 頻寬統計視窗（秒），到期重算 |
| `BW_IP_SOFT_MB` | `100` | 單 IP 每視窗流量，超過開始限速 |
| `BW_FOLDER_HARD_GB` | `5` | 每資料夾每視窗上限 |
| `BW_FOLDERS_PER_WINDOW` | `10` | 單 IP 每視窗觸及資料夾數上限 |
| `THROTTLE_MAX_MBPS` / `THROTTLE_MIN_MBPS` | `90` / `40` | 限速起點與下限（每多 1 GB 降 10） |

用戶端 IP 從 `CF-Connecting-IP` → `X-Forwarded-For` → 連線位址依序取得，
Cloudflare 後面也能正確限速。登入 session 不限速。

產生的連結走 `app/urls.py`：HTTPS 進來就回 HTTPS（讀 `Forwarded` /
`X-Forwarded-Proto` / `X-Forwarded-Host`），代理沒帶標頭就設
`PUBLIC_BASE_URL` 強制指定網域。這兩個標頭會被信任，所以直連後端埠時
請防火牆擋住，或直接用 `PUBLIC_BASE_URL` 釘死網域。

公開上傳的 `folder` 欄位吃兩種東西：既有資料夾 id，或任意文字（自動開一個
以它為名字的新資料夾並上傳進去）。要「只建資料夾、不傳檔」就
`POST /api/public/folder {"name": "..."}`，或網頁的「建立資料夾」分頁。

私人區除了登入 cookie，也接受 **`?auth=<PASSWORD>`**（每個請求都帶）。這是為
了走 CORS 型代理的客戶端：代理會轉送請求，但 `Set-Cookie` 回不到瀏覽器，
cookie session 在那條路上無效。只在 HTTPS 生效、密碼不會被回寫到任何回應或
轉址、同一 IP 猜錯 10 次鎖 10 分鐘。

檔案 id 就是內容的 sha256：`file_id` 相同代表位元組完全相同。位元組只存一份
在 `BIN_DIR`（預設 `bin/`），所以同一個檔案傳十次還是只有一份，連結也一樣。
資料夾 / 單檔目錄裡只放 `<file_id>.json`（檔名、型別、大小、說明、所属資料夾）。
刪掉最後一個引用時才會真的刪位元組。舊的 UUID 檔案 id 仍可下載。

分享連結有兩種：完整直連（`/dl/s/<sha256>`）與 **短網址**
`/usercontent/<6碼>.<ext>`——取 sha256 最短的唯一前綴，撞到別的檔案就自動
加長到 7、8 碼…，並帶 `Cache-Control: immutable`，網址永不失效，直接丟給
Cloudflare 快取即可（`usercontent.qiuhuang.dev` 指向同一台機器的那個路徑）。
上傳也可以帶自由文字說明：`description`（表單欄位或 merge 的 JSON key）。

## 法律條款

`/legal`（= `/docs/legal`）是繁中／English 雙語條款，套用**臺灣**法律：
可接受使用政策、《著作權法》第六章之一的通知－取下流程（權利人補正期限
7 個工作天；臺灣沒有 DMCA）、隱私。兒少性影像零容忍，依《兒童及少年性
剝削防制條例》第 36／38／39 條，業者須於知悉後 24 小時內限制瀏覽或移除。
每頁底部都有連到條款的連結。

## 文件

- 站內指南：`/docs`、`/docs/quickstart`、`/docs/api`、`/docs/limits`
- AI 用文件：`/llms.txt`（英文，給機器讀）
- 同步的 Markdown 來源在 `docs/`，方便在 GitHub 瀏覽。
