# 自行架設

CaveMan Drop 是一支普通 FastAPI 應用：給它一個 Python（3.11+）、一個目錄放檔案，
加上一組 `.env` 就能跑。這頁涵蓋安裝、設定、開機自動更新與放在反向代理後面。

## 安裝與執行

```bash
git clone https://github.com/ChiuHuang/caveman-drop
cd caveman-drop

cp .env.example .env    # 至少改 PASSWORD

uv venv
uv pip install -r requirements.txt
uv run main.py
# 或：uv run uvicorn main:app --host 0.0.0.0 --port 20042
# 或（正式環境）：.venv/bin/python -m gunicorn app:app -w 1 \
#   -k uvicorn.workers.UvicornWorker -b 0.0.0.0:20042
```

`requirements.txt` 已包含 gunicorn，適合 systemd 常駐。

## 開機啟動 / 自動更新：`deploy.sh`

`deploy.sh` 是 POSIX sh，適合丟給 systemd、pelican/pterodactyl 或 cron 使用：

1. 第一次執行會 `git init` 並對齊 `origin/main`；之後每次執行
   `git pull --ff-only` 自動更新（`AUTO_UPDATE=1` 時）。
2. 沒有 `.venv` 就建一個；沒有 `.env` 就從 `.env.example` 複製。
3. `requirements.txt` 的 sha256 有變才重新 `pip install`。
4. 最後啟動 gunicorn 監聽 `0.0.0.0:20042`。

systemd 範例（把 `WorkingDirectory` 換成你的路徑）：

```ini
[Unit]
Description=CaveMan Drop
After=network.target

[Service]
WorkingDirectory=/srv/caveman-drop
ExecStart=/bin/sh ./deploy.sh
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

## 設定（.env）

| 變數 | 預設 | 用途 |
|---|---|---|
| `PORT`（`SERVER_PORT` 也可）/ `HOST` | `20042` / `0.0.0.0` | 監聽位址 |
| `PASSWORD` | `passw` | 私人後台密碼——**務必修改** |
| `SECRET_KEY` | 自動產生 | Session 簽名（存於 `.secret_key`） |
| `PUBLIC_BASE_URL` | 空 | 產生連結的固定基底網址；留空＝跟著請求走 |
| `PRIVATE_ONLY_HOSTS` | `pvf.chiuhuang.dev` | 只給登入用的網域（逗號分隔） |
| `UPLOAD_DIR` / `TMP_DIR` / `PUBLIC_DIR` / `SINGLE_DIR` | `airdrop_files` / `airdrop_tmp` / `public_uploads` / `public_singles` | 儲存目錄 |
| `BIN_DIR` | `bin` | sha256 位元組庫（同一份內容只存一份） |
| `MAX_FILE_SIZE_GB` / `MAX_CHUNKED_PARTS` | `5` / `16384` | 公開單檔上限／分段數上限 |
| `TMP_MAX_AGE_HOURS` | `24` | 遺棄的分塊目錄多久清掉 |
| `RATE_LIMIT_WINDOW_SECONDS` / `RATE_LIMIT_MAX_UPLOADS` | `3600` / `30` | 單 IP 上傳頻率限制 |
| `BW_WINDOW_SECONDS` | `600` | 頻寬統計視窗（秒），到期重算 |
| `BW_IP_SOFT_MB` | `100` | 單 IP 每視窗流量，超過開始限速 |
| `BW_FOLDER_HARD_GB` | `5` | 每資料夾每視窗上限 |
| `BW_FOLDERS_PER_WINDOW` | `10` | 單 IP 每視窗觸及資料夾數上限 |
| `THROTTLE_MAX_MBPS` / `THROTTLE_MIN_MBPS` | `90` / `40` | 限速起點與下限 |
| `BW_TIER_GB` / `BW_TIER_MBPS` | `1` / `10` | 每多 1 GB 降 10 Mbps |

## 反向代理與連結方向

- 用戶端 IP 從 `CF-Connecting-IP` → `X-Forwarded-For` → 連線位址依序取得，
  Cloudflare 後面也能正確限速；登入 session 不限速。
- 產生的連結走 `app/urls.py`：HTTPS 進來就回 HTTPS（讀 `Forwarded` /
  `X-Forwarded-Proto` / `X-Forwarded-Host`）。代理沒帶標頭就設
  `PUBLIC_BASE_URL` 釘死網域。
- 這些標頭會被信任：直連後端埠請用防火牆擋住，或直接設 `PUBLIC_BASE_URL`。
- 短網址 `/<code>.<ext>` 帶 `Cache-Control: immutable`，
  可以單獨指到同一台機器的這個路徑交給 CDN 快取。

## 儲存與清理

- `file_id` 就是內容的 sha256：位元組只存一份在 `BIN_DIR`（預設 `bin/`），
  重複上傳不會多佔空間。刪掉最後一個引用時才會真的刪位元組。
- 分段上傳的暫存分塊放 `TMP_DIR`，超過 `TMP_MAX_AGE_HOURS`（預設 24 小時）
  的遺棄目錄由後台掃描器自動刪除。
- 公開單檔（無資料夾）放 `SINGLE_DIR`；帶資料夾的公開檔與清單放 `PUBLIC_DIR`；
  私人檔案放 `UPLOAD_DIR`。

## 介面語言

語言由**瀏覽器**決定：每頁 `<head>` 中的內嵌腳本讀 `navigator.languages`
（zh-TW／Hant／HK／MO → 繁體中文，其他 → English），寫入 `lang` cookie 並在
第一次需要換頁時 reload 一次。`?lang=zh-TW` / `?lang=en` 可手動覆寫。
JSON、純文字與 `/llms.txt` 固定英文，腳本完全不必關心語言。
