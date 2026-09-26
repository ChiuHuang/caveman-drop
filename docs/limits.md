# 限制與規範

透過 `.env` 設定（見 `.env.example`）。

- **單檔上限：** `MAX_FILE_SIZE_GB`（預設 5 GB），一律強制執行——串流寫入
  超過上限會中斷並清理。
- **多人資料夾：** 資料夾超過 1 個檔案後，合計上限為
  `MAX_MULTI_FOLDER_TOTAL_GB`（預設 1 GB）。只有一個檔案時只受單檔上限
  約束。同資料夾的並行上傳會序列化，避免配額被競爭繞過。
- **頻率限制：** 每 IP 每 `RATE_LIMIT_WINDOW_SECONDS` 秒最多
  `RATE_LIMIT_MAX_UPLOADS` 次上傳（預設每小時 30 次）。超過回 `429`。
  分段上傳只在合併時扣一次。
- **頻寬（滑動 60 秒視窗）：** 每 IP 每分鐘 1 GB，每資料夾每分鐘 5 GB。
  單 IP 每分鐘超過 `BW_IP_SOFT_MB`（預設 100 MB）或觸及超過
  `BW_FOLDERS_PER_MIN`（預設 10）個資料夾，該 IP 被限速到 `THROTTLE_MBPS`
  （預設 90 Mbps）並鎖定單線程（linear），直到用量回落。超速時分塊回應會
  直接告訴你 `threads: 1`。
- **CORS：** 公開 API 接受跨來源呼叫，任何網站的 JS 與 AI 都可直接上傳。
- **公開分享無驗證：** 知道資料夾 id 的人都能加檔案。請把資料夾 id 當成
  通行證，只分享給你信任的人。
