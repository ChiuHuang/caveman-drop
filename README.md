# CaveMan Drop

免帳號、純文字優先的檔案分享。從任何腳本、瀏覽器或 AI 上傳檔案——立刻拿回永久連結。公開分享不需要帳號。

- **瀏覽器**在每個頁面與端點都看到 Material Design 3 介面（MDUI v2）。
- **腳本與 AI**（`curl`、Python、AI 工具）透過內容協商拿到純 JSON / 純文字。加上 `?format=json` 或 `?format=html` 可強制指定。
- 機器可讀文件在 `/llms.txt`；完整 API 索引在 `/api`。
- 登入後進入**私人模式**：只有私人空間（含 16 線程分段上傳），不再顯示公開上傳。

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
  storage.py         # 檔案儲存、配額、速率限制、下載
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
| `PASSWORD` | `passw` | 私人後台密碼——**務必修改** |
| `SECRET_KEY` | 自動產生 | Session 簽名（存於 `.secret_key`） |
| `UPLOAD_DIR` / `TMP_DIR` / `PUBLIC_DIR` | `airdrop_files` / `airdrop_tmp` / `public_uploads` | 儲存目錄 |
| `MAX_FILE_SIZE_GB` | `5` | 單檔上限 |
| `MAX_MULTI_FOLDER_TOTAL_GB` | `1` | 資料夾超過 1 個檔案後的合計上限 |
| `RATE_LIMIT_MAX_UPLOADS` / `RATE_LIMIT_WINDOW_SECONDS` | `30` / `3600` | 單 IP 上傳頻率限制 |

## 文件

- 站內指南：`/docs`、`/docs/quickstart`、`/docs/api`、`/docs/limits`
- AI 用文件：`/llms.txt`（英文，給機器讀）
- 同步的 Markdown 來源在 `docs/`，方便在 GitHub 瀏覽。
