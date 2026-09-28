// CaveMan Drop 瀏覽器互動：側欄、主題、複製、分段上傳、並行下載、預覽、刪除確認。
(function () {
  const THREADS = 16;
  const CHUNK = 4 * 1024 * 1024;
  // 用前幾個 chunk 決定並行數：量到 ADAPT_MS 的實際傳輸、或 ADAPT_CHUNKS 個塊
  const ADAPT_MS = 2000;
  const ADAPT_MAX_MS = 6000;
  const ADAPT_CHUNKS = 6;
  const ADAPT_BYTES = 4 * 1024 * 1024;

  // 語言跟著 IP（見 app/i18n）：台灣網段中文，其他英文
  const LANG = (document.documentElement && document.documentElement.dataset.lang) === "zh-TW"
    ? "zh-TW" : "en";
  const T = {
    zh: {
      copied: "連結已複製", copyFail: "複製失敗", needFile: "請先選擇檔案",
      fail: "上傳失敗：", mergeFail: "合併失敗：", merging: "合併中…", done: "上傳完成",
      folderMade: "資料夾已建立", folderFail: "無法建立資料夾", needName: "請輸入資料夾名稱",
      mkdirOk: "資料夾已建立", mkdirFail: "建立失敗", shareOk: "分享連結已建立",
      unshareOk: "已取消分享", unshareFail: "取消失敗", moveFail: "移動失敗",
      moved: "已移到 ", movedOut: "已移出資料夾", noCross: "不能跨公開／私人移動",
      switchTab: "先切到可以上傳的分頁", uploadedTo: "已上傳到 ", deleted: "已刪除",
      deleteFail: "刪除失敗", dlDone: "下載完成", dlFail: "下載失敗，改用直接下載",
      theme: "主題：", dark: "深色", light: "淺色", auto: "自動",
      pause: "暫停", resume: "繼續", paused: "已暫停", idle: "待命中",
      live: "上傳中 #", chunkDone: "完成 #", failed: "失敗",
      segLabel: "分段：", threads: " · ", segUnit: " 線程",
      speed: "{rate}/s（{mbps} Mbps）· {sent} / {total}{left}",
      left: " · 剩 {t}", speedDone: "完成 · 平均 {rate}/s",
      link: "連線 {mbps} Mbps · {n} 線程",
      throttled: "分享頻寬限速中（約 {mbps} Mbps），上傳繼續",
      sec: " 秒", min: " 分 ", hour: " 小時 ",
      upDone: "上傳完成", folderCreated: "資料夾已建立",
      stats: "{size} · {secs} 秒 · 平均 {rate}/s{dup}", dup: " · 內容已存在，未重複儲存",
      rowLink: "連結", rowFile: "檔案", rowDirect: "直連", rowFolder: "資料夾",
      copy: "複製", open: "開啟", preview: "預覽", close: "關閉",
      dropUpload: "放開手上傳", dropInto: "放到「{name}」", dropFolder: "放到這個資料夾",
      multi: "上傳 {i}/{n}：{name}", previewTitle: "預覽 — ",
    },
    en: {
      copied: "Link copied", copyFail: "Copy failed", needFile: "Pick a file first",
      fail: "Upload failed: ", mergeFail: "Merge failed: ", merging: "Merging…", done: "Upload complete",
      folderMade: "Folder created", folderFail: "Could not create the folder", needName: "Give the folder a name",
      mkdirOk: "Folder created", mkdirFail: "Could not create", shareOk: "Share link created",
      unshareOk: "Share revoked", unshareFail: "Could not revoke", moveFail: "Move failed",
      moved: "Moved to ", movedOut: "Removed from folder", noCross: "Cannot move across public and private",
      switchTab: "Switch to an upload tab first", uploadedTo: "Uploaded to ", deleted: "Deleted",
      deleteFail: "Delete failed", dlDone: "Download complete", dlFail: "Download failed, using a direct link",
      theme: "Theme: ", dark: "Dark", light: "Light", auto: "Auto",
      pause: "Pause", resume: "Resume", paused: "Paused", idle: "Idle",
      live: "Uploading #", chunkDone: "Done #", failed: "Failed",
      segLabel: "Segments: ", threads: " · ", segUnit: " threads",
      speed: "{rate}/s ({mbps} Mbps) · {sent} / {total}{left}",
      left: " · {t} left", speedDone: "Done · {rate}/s average",
      link: "{mbps} Mbps · {n} threads",
      throttled: "Bandwidth throttled to about {mbps} Mbps, still uploading",
      sec: "s", min: "m ", hour: "h ",
      upDone: "Upload complete", folderCreated: "Folder created",
      stats: "{size} · {secs}s · {rate}/s average{dup}", dup: " · already stored, not duplicated",
      rowLink: "Link", rowFile: "File", rowDirect: "Direct", rowFolder: "Folder",
      copy: "Copy", open: "Open", preview: "Preview", close: "Close",
      dropUpload: "Drop to upload", dropInto: "Drop into “{name}”", dropFolder: "Drop into this folder",
      multi: "Uploading {i}/{n}: {name}", previewTitle: "Preview — ",
    },
  };
  const S = T[LANG === "zh-TW" ? "zh" : "en"];
  const fill = (tpl, kw) => tpl.replace(/\{(\w+)\}/g, (m, k) => (k in kw ? kw[k] : m));
  const CONFIRM = {
    dir: { zh: "確定刪除資料夾「{name}」（含 {n} 個檔案）嗎？無法復原。",
           en: "Delete folder \u201c{name}\u201d and its {n} files? This cannot be undone." },
    pubdir: { zh: "確定刪除公開資料夾「{name}」（含 {n} 個檔案）嗎？",
              en: "Delete public folder \u201c{name}\u201d and its {n} files?" },
    file: { zh: "確定要刪除「{name}」嗎？此動作無法復原。",
            en: "Delete \u201c{name}\u201d? This cannot be undone." },
    unshare: { zh: "確定取消這個分享連結嗎？", en: "Revoke this share link?" },
  };
  const key = LANG === "zh-TW" ? "zh" : "en";
  const folderConfirm = (n, c) => fill(CONFIRM.dir[key], { name: n, n: c });
  const pubFolderConfirm = (n, c) => fill(CONFIRM.pubdir[key], { name: n, n: c });
  const fileConfirm = (n) => fill(CONFIRM.file[key], { name: n });

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  window.toast = function (msg) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.open = true;
  };

  async function copyText(text, okMsg) {
    try {
      await navigator.clipboard.writeText(text);
      window.toast(okMsg || S.copied);
    } catch { window.toast(S.copyFail); }
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function fmtMB(n) {
    if (!(n > 0)) return "0 B";
    if (n < 1024) return n.toFixed(0) + " B";
    if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
    if (n < 1073741824) return (n / 1048576).toFixed(1) + " MB";
    return (n / 1073741824).toFixed(2) + " GB";
  }

  // 連結欄位的值（mdui-text-field 或原生 input 都吃）
  function fieldValue(root, name) {
    const el = root.querySelector(`[name="${name}"]`);
    if (!el) return "";
    const inner = el.querySelector ? el.querySelector("input,textarea") : null;
    return String(el.value != null && el.value !== "" ? el.value : inner ? inner.value : "").trim();
  }

  function fmtDur(s) {
    if (!(s > 0) || !isFinite(s)) return "";
    if (s < 60) return Math.round(s) + S.sec;
    const m = Math.floor(s / 60);
    return m < 60 ? `${m}${S.min}${Math.round(s % 60)}${S.sec}` : `${Math.floor(m / 60)}${S.hour}${m % 60}${S.min}`;
  }

  // XHR upload so we get real byte-level progress (fetch cannot report it).
  // onByte(loaded) fires as the body actually leaves the browser, which is what
  // the speed readout and the progress bar should follow.
  function xhrPost(url, formData, onByte) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url, true);
      xhr.responseType = "text";
      if (onByte) {
        xhr.upload.onprogress = (ev) => onByte(ev.loaded);
      }
      xhr.onload = () => {
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error("HTTP " + xhr.status));
          return;
        }
        let data = {};
        try { data = JSON.parse(xhr.responseText || "{}"); } catch { /* 非 JSON 就忽略 */ }
        resolve(data);
      };
      xhr.onerror = () => reject(new Error("network error"));
      xhr.onabort = () => reject(new Error("aborted"));
      xhr.send(formData);
    });
  }

  // 與伺服器 storage.threads_for_speed 同一組門檻（十進位 MB/s，對應 80/40/16 Mbps）
  function threadsForSpeed(bps) {
    if (bps >= 10000000) return 16;
    if (bps >= 5000000) return 32;
    if (bps >= 2000000) return 64;
    return 128;
  }

  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  function linkRow(label, url, buttons) {
    return `<div class="rlink"><span class="rlink-label">${esc(label)}</span><code>${esc(url)}</code>` +
      `<span class="rlink-btns">${buttons}</span></div>`;
  }

  function resultCard(title, note, stats, rows) {
    return `<mdui-card variant="filled" class="card-pad result-box">
      <div class="result-title"><strong>${esc(title)}</strong>${note ? `<span class="muted">${esc(note)}</span>` : ""}</div>
      ${stats ? `<div class="result-stats">${esc(stats)}</div>` : ""}
      ${rows.join("")}
    </mdui-card>`;
  }

  // ---- 分段上傳（含線程表 + 分段條 + 測速 + 暫停）----
  async function chunkedUpload(form) {
    const input = form.querySelector('input[type="file"]');
    const file = input && input.files[0];
    if (!file) { window.toast(S.needFile); return; }
    const mergeUrl = form.getAttribute("data-merge");
    const isPublic = form.hasAttribute("data-public");
    const btn = form.querySelector("[type=submit]");
    const panel = form.querySelector("[data-tp]");
    const pct = panel && panel.querySelector("[data-tp-pct]");
    const speed = panel && panel.querySelector("[data-tp-speed]");
    const note = panel && panel.querySelector("[data-tp-note]");
    const bar = panel && panel.querySelector("[data-tp-bar]");
    const segsBox = panel && panel.querySelector("[data-tp-segs]");
    const segCount = panel && panel.querySelector("[data-tp-segcount]");
    const rowsBox = panel && panel.querySelector("[data-tp-rows]");
    const pauseBtn = panel && panel.querySelector("[data-tp-pause]");

    const total = Math.max(1, Math.ceil(file.size / CHUNK));
    const uploadId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()));
    const startedAt = performance.now();
    // 不用另外探針：先照 16 線程送，用前幾個 chunk 量到的真實速度決定要不要加線程。
    const state = {
      next: 0, done: 0, sentBytes: 0, failed: null,
      paused: false, cancelled: false, maxThreads: Math.min(THREADS, total),
    };
    // 用前幾個 chunk 量到的真實速度決定並行數。量測視窗從「第一個位元組真的
    // 送出」開始算，所以不會把 16 條連線的 TLS 握手算成慢速。
    const adapt = { first: 0, bytes: 0, chunks: 0, locked: total <= ADAPT_CHUNKS };

    if (btn) btn.loading = true;
    if (panel) { panel.hidden = false; panel.__state = state; }
    if (pauseBtn) { pauseBtn.textContent = "暫停"; }
    if (panel) panel.classList.remove("paused");

    // 線程表：最多顯示 16 列，人多時輪流顯示
    const shown = Math.min(Math.max(ADAPT_CHUNKS * 2, 16), 16);
    const rowEls = [];
    if (rowsBox) {
      rowsBox.innerHTML = "";
      for (let t = 0; t < shown; t++) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${t + 1}</td><td class="st idle">${S.idle}</td>`;
        rowsBox.appendChild(tr);
        rowEls.push(tr.querySelector(".st"));
      }
    }
    // 分段條：最多 144 格，分塊映射到格子
    const NCELL = Math.min(total, 144);
    const cellOf = (i) => Math.floor((i * NCELL) / total);
    const cellEls = [], cellNeed = new Array(NCELL).fill(0), cellGot = new Array(NCELL).fill(0);
    for (let i = 0; i < total; i++) cellNeed[cellOf(i)]++;
    if (segsBox) {
      segsBox.innerHTML = "";
      for (let k = 0; k < NCELL; k++) {
        const s = document.createElement("i");
        segsBox.appendChild(s);
        cellEls.push(s);
      }
    }
    const segLabel = () => `${total} / ${NCELL}`
      + (state.maxThreads > 16 ? `${S.threads}${state.maxThreads}${S.segUnit}` : "");
    if (segCount) segCount.textContent = segLabel();
    const setRow = (t, txt, cls) => {
      const el = rowEls.length ? rowEls[t % rowEls.length] : null;
      if (!el) return;
      el.textContent = txt;
      el.className = "st " + cls;
    };
    const render = () => {
      const frac = file.size ? Math.min(1, state.sentBytes / file.size) : state.done / total;
      if (pct) pct.textContent = Math.floor(frac * 100) + "%";
      if (bar) bar.value = frac;
    };
    render();

    // 測速：每 0.25 秒結算，用真正經過的時間（不是假定的間隔）＋平滑
    let lastAt = startedAt, lastSent = 0, ema = 0;
    const speedTimer = setInterval(() => {
      const t = performance.now();
      const dt = Math.max((t - lastAt) / 1000, 0.05);
      const inst = Math.max(0, state.sentBytes - lastSent) / dt;   // 目前這一瞬間的速率
      lastAt = t;
      lastSent = state.sentBytes;
      ema = ema ? ema + (inst - ema) * 0.4 : inst;
      // 前幾個 chunk 量到的真實速度 → 決定要加還是減並行數
      const streaming = adapt.first ? t - adapt.first : 0;
      const sampled = state.sentBytes - adapt.bytes;
      if (!adapt.locked && !state.paused && adapt.first && state.done < total
          && ((streaming >= ADAPT_MS && sampled >= ADAPT_BYTES)
              || adapt.chunks >= ADAPT_CHUNKS || streaming >= ADAPT_MAX_MS)) {
        const bps = sampled / Math.max(streaming / 1000, 0.05);
        const want = Math.max(1, Math.min(128, threadsForSpeed(bps), total));
        adapt.locked = true;
        state.maxThreads = want;
        if (want > started) addWorkers(want - started);
        if (note) note.textContent = fill(S.link, { mbps: (bps * 8 / 1e6).toFixed(0), n: want });
        if (segCount) segCount.textContent = segLabel();
      }
      if (speed) {
        if (state.paused) {
          speed.textContent = S.paused;
        } else if (state.done >= total) {
          const avg = state.sentBytes / Math.max((t - startedAt) / 1000, 0.001);
          speed.textContent = fill(S.speedDone, { rate: fmtMB(avg) });
        } else {
          const left = ema > 1 ? fmtDur((file.size - state.sentBytes) / ema) : "";
          speed.textContent = fill(S.speed, {
            rate: fmtMB(ema), mbps: (ema * 8 / 1e6).toFixed(0),
            sent: fmtMB(state.sentBytes), total: fmtMB(file.size),
            left: left ? fill(S.left, { t: left }) : "",
          });
        }
      }
      if (panel) {
        const mbs = ema / 1048576;
        panel.style.setProperty("--pulse-dur", mbs > 50 ? ".3s" : mbs > 10 ? ".6s" : mbs > 0.5 ? "1.2s" : "2s");
      }
    }, 250);
    // 暫停鈕只掛一次監聽，狀態存在 panel 上（同一頁第二次上傳才不會雙重觸發）
    if (pauseBtn && !pauseBtn.dataset.bound) {
      pauseBtn.dataset.bound = "1";
      pauseBtn.addEventListener("click", () => {
        const st = panel && panel.__state;
        if (!st) return;
        st.paused = !st.paused;
        pauseBtn.textContent = st.paused ? S.resume : S.pause;
        if (panel) panel.classList.toggle("paused", st.paused);
        window.toast(st.paused ? S.paused : S.paused);
      });
    }

    async function worker(t) {
      while (true) {
        if (state.failed || state.cancelled) return;
        while (state.paused && !state.failed) await sleep(200);
        if (t >= state.maxThreads) { setRow(t, S.idle, "idle"); return; }
        if (state.next >= total) { setRow(t, S.idle, "idle"); return; }
        const i = state.next++;
        setRow(t, `${S.live}${i + 1}`, "live");
        const cell = cellOf(i);
        if (cellEls[cell]) cellEls[cell].classList.add("active");
        const part = file.slice(i * CHUNK, (i + 1) * CHUNK);
        const fd = new FormData();
        fd.append("file_chunk", part, "chunk");
        fd.append("upload_id", uploadId);
        fd.append("index", String(i));
        fd.append("filename", file.name);
        // 進度事件回報「真的送出去多少位元組」，速度與百分比都跟著它走
        let counted = 0;
        try {
          const js = await xhrPost(form.action, fd, (loaded) => {
            const v = Math.max(0, Math.min(loaded, part.size) - counted);
            counted = Math.min(loaded, part.size);
            if (!adapt.first) {          // 第一個位元組真正送出的時間
              adapt.first = performance.now();
              adapt.bytes = state.sentBytes;
            }
            state.sentBytes += v;
            render();
          });
          if (js && js.throttled && note) {
            note.textContent = fill(S.throttled, { mbps: js.throttle_mbps || 90 });
            if (panel) panel.classList.add("throttled");
          }
        } catch (err) {
          state.sentBytes -= counted;
          state.failed = err;
          setRow(t, S.failed, "err");
          return;
        }
        state.done++;
        adapt.chunks++;
        cellGot[cell]++;
        if (cellGot[cell] >= cellNeed[cell] && cellEls[cell]) {
          cellEls[cell].classList.remove("active");
          cellEls[cell].classList.add("done");
        }
        setRow(t, `${S.chunkDone}${i + 1}`, "ok");
        render();
      }
    }

    // 線程池：先 16 條起步，量到慢連線就再往上加（多開的沒任務就自己結束）
    let started = 0, running = 0, settle;
    const allDone = new Promise((res) => { settle = res; });
    function addWorkers(n) {
      for (let k = 0; k < n; k++) {
        const t = started++;
        running++;
        worker(t).then(() => { if (--running === 0) settle(); });
      }
    }
    addWorkers(Math.min(THREADS, total));
    await allDone;
    clearInterval(speedTimer);
    if (state.failed) {
      window.toast(S.fail + state.failed.message);
      if (btn) btn.loading = false;
      return;
    }
    if (pct) pct.textContent = S.merging;
    const elapsed = Math.max((performance.now() - startedAt) / 1000, 0.001);
    try {
      const body = { upload_id: uploadId, filename: file.name, total_chunks: total };
      const desc = fieldValue(form, "description");
      if (desc) body.description = desc;
      if (isPublic) {
        const folderText = fieldValue(form, "folder");  // 既有資料夾 ID 或自訂名稱都能用
        if (folderText) body.folder = folderText;
      } else {
        const fid = fieldValue(form, "folder_id");
        if (fid) body.folder_id = fid;
      }
      const token = fieldValue(form, "token");
      if (token) body.token = token;
      const res = await fetch(mergeUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
      if (btn) btn.loading = false;
      if (isPublic) {
        const out = form.parentElement.querySelector("[data-upload-result]");
        const durl = data.download_url || data.url;
        const furl = data.folder_url || data.share_url;
        const share = data.short_url || durl;   // catbox-style short link when we have one
        const secs = elapsed < 10 ? elapsed.toFixed(1) : Math.round(elapsed);
        const rows = [];
        if (share && share !== durl) {
          rows.push(linkRow(S.rowLink, share,
            `<mdui-button variant="text" data-copy="${esc(share)}">${esc(S.copy)}</mdui-button>` +
            `<a href="${esc(share)}"><mdui-button variant="text">${esc(S.open)}</mdui-button></a>`));
        }
        rows.push(linkRow(share === durl ? S.rowFile : S.rowDirect, durl,
          `<mdui-button variant="text" data-preview="${esc(durl)}?preview=1" data-name="${esc(data.filename)}">${esc(S.preview)}</mdui-button>` +
          `<mdui-button variant="text" data-copy="${esc(durl)}">${esc(S.copy)}</mdui-button>`));
        if (furl) {
          rows.push(linkRow(S.rowFolder, furl,
            `<a href="${esc(furl)}"><mdui-button variant="text">${esc(S.open)}</mdui-button></a>` +
            `<mdui-button variant="text" data-copy="${esc(furl)}">${esc(S.copy)}</mdui-button>`));
        }
        const stats = fill(S.stats, {
          size: fmtMB(data.size_bytes), secs, rate: fmtMB(data.size_bytes / elapsed),
          dup: data.deduplicated ? S.dup : "",
        });
        const html = resultCard(S.upDone, data.filename, stats, rows);
        if (out) out.innerHTML = html;
        if (panel) panel.hidden = true;
        window.toast(S.done);
      } else {
        window.toast(S.done);
        window.location.reload();
      }
    } catch (err) {
      window.toast(S.mergeFail + err.message);
      if (btn) btn.loading = false;
    }
  }

  // ---- 並行下載：Range 分段並行抓取後合併 ----
  async function mtDownload(btn) {
    const url = btn.getAttribute("data-mt-download");
    const name = btn.getAttribute("data-name") || "download";
    let size = parseInt(btn.getAttribute("data-size") || "0", 10);
    btn.loading = true;
    try {
      if (!size) {
        // 取第一個位元組，從 Content-Range 得知總長度
        const probe = await fetch(url, { headers: { Range: "bytes=0-0" } });
        const cr = probe.headers.get("Content-Range") || "";
        const m = cr.match(/\/(\d+)\s*$/);
        if (m) size = parseInt(m[1], 10);
      }
      if (!size) { window.location.href = url; return; } // 後備：直接下載
      const n = Math.min(THREADS, Math.max(1, Math.ceil(size / (256 * 1024))));
      const part = Math.ceil(size / n);
      window.toast(`${name}`);
      const bufs = new Array(n);
      let cursor = 0;
      async function worker() {
        while (cursor < n) {
          const i = cursor++;
          const start = i * part;
          const end = Math.min(start + part - 1, size - 1);
          const res = await fetch(url, { headers: { Range: `bytes=${start}-${end}` } });
          if (!res.ok && res.status !== 206) throw new Error("HTTP " + res.status);
          bufs[i] = await res.arrayBuffer();
        }
      }
      await Promise.all(Array.from({ length: n }, worker));
      const blob = new Blob(bufs.map((b) => new Uint8Array(b)));
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
      window.toast(S.dlDone);
    } catch (err) {
      window.toast(S.dlFail);
      window.location.href = url;
    } finally { btn.loading = false; }
  }

  // ---- 預覽：對話框內嵌 iframe ----
  function preview(url, name) {
    const dlg = document.createElement("mdui-dialog");
    dlg.setAttribute("headline", S.previewTitle + name);
    dlg.innerHTML = `<iframe src="${url}" style="width:100%;height:60vh;border:0;border-radius:8px" title="preview"></iframe>
      <mdui-button slot="action" variant="text">${esc(S.close)}</mdui-button>`;
    document.body.appendChild(dlg);
    dlg.querySelector("mdui-button").addEventListener("click", () => { dlg.open = false; setTimeout(() => dlg.remove(), 300); });
    dlg.open = true;
  }

  // ---- 拖放：拖檔案進資料夾、拖檔案列換資料夾、整頁拖放上傳 ----
  function pickFile(input, file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
  }

  function formForScope(scope) {
    const forms = Array.from(document.querySelectorAll("form[data-chunked]"))
      .filter((f) => f.offsetParent !== null);   // visible tab only
    return forms.find((f) => (scope === "public") === f.hasAttribute("data-public")) || null;
  }

  function visibleScope() {
    const panel = Array.from(document.querySelectorAll("[data-tabpanel]")).find((p) => !p.hidden);
    return panel && panel.querySelector('form[data-chunked][data-public]') ? "public" : "private";
  }

  function setTargetFolder(form, scope, folderId) {
    if (scope === "public") {
      const field = form.querySelector('[name="folder"]');
      if (field) {
        if (field.tagName.toLowerCase() === "input") field.value = folderId;
        else field.value = folderId;
      }
      return;
    }
    const sel = form.querySelector('[name="folder_id"]');
    if (sel) sel.value = folderId || "";
  }

  async function uploadDropped(files, scope, folderId, label) {
    const form = formForScope(scope);
    if (!form) { window.toast(S.switchTab); return; }
    const input = form.querySelector('input[type="file"]');
    setTargetFolder(form, scope, folderId);
    const list = Array.from(files);
    for (let i = 0; i < list.length; i++) {
      if (list.length > 1) window.toast(fill(S.multi, { i: i + 1, n: list.length, name: list[i].name }));
      pickFile(input, list[i]);
      await chunkedUpload(form);
    }
    if (list.length > 1) window.location.reload();
    else if (label) window.toast(S.uploadedTo + label);
  }

  async function moveDropped(fileId, scope, folderId, label, fromFolder) {
    const url = scope === "public" ? "/api/public/move" : "/api/files/move";
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_id: fileId,
          folder_id: folderId || null,
          from_folder_id: fromFolder || null,
        }),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      window.toast(label ? S.moved + label : S.movedOut);
      window.location.reload();
    } catch { window.toast(S.moveFail); }
  }

  const MOVE_MIME = "application/x-caveman-move";

  function installDragDrop() {
    const root = document.querySelector("[data-droproot]");
    if (!root) return;
    const hint = root.querySelector("[data-drophint]");

    const highlight = (el, on) => {
      if (!el) return;
      el.classList.toggle("dragover", on);
      if (hint) hint.hidden = !on;
    };

    // dragging an existing file row out of a list
    root.addEventListener("dragstart", (ev) => {
      const row = ev.target.closest ? ev.target.closest("[data-move]") : null;
      if (!row) return;
      const payload = JSON.stringify({
        kind: "move",
        id: row.getAttribute("data-move"),
        scope: row.getAttribute("data-scope"),
        from: row.getAttribute("data-from") || "",
        name: row.getAttribute("data-name"),
      });
      ev.dataTransfer.setData(MOVE_MIME, payload);
      ev.dataTransfer.setData("text/plain", row.getAttribute("data-name") || "");
      ev.dataTransfer.effectAllowed = "move";
      row.classList.add("dragging");
    });
    root.addEventListener("dragend", (ev) => {
      const row = ev.target.closest ? ev.target.closest("[data-move]") : null;
      if (row) row.classList.remove("dragging");
      root.querySelectorAll(".dragover").forEach((el) => el.classList.remove("dragover"));
      if (hint) hint.hidden = true;
    });

    root.addEventListener("dragover", (ev) => {
      if (!hasFiles(ev)) return;
      ev.preventDefault();
      const target = ev.target.closest ? ev.target.closest("[data-dropscope]") : null;
      ev.dataTransfer.dropEffect = target && scopeOf(target) === "private" ? "copy" : "copy";
      root.querySelectorAll(".dragover").forEach((el) => el.classList.remove("dragover"));
      highlight(target, true);
      if (hint) hint.textContent = target ? dropLabel(target) : S.dropUpload;
    });

    root.addEventListener("dragleave", (ev) => {
      const target = ev.target.closest ? ev.target.closest("[data-dropscope]") : null;
      if (target && !target.contains(ev.relatedTarget)) highlight(target, false);
    });

    root.addEventListener("drop", async (ev) => {
      if (!hasFiles(ev)) return;
      ev.preventDefault();
      const target = ev.target.closest ? ev.target.closest("[data-dropscope]") : null;
      root.querySelectorAll(".dragover").forEach((el) => el.classList.remove("dragover"));
      if (hint) hint.hidden = true;
      const move = readMove(ev);
      if (target) {
        const scope = scopeOf(target) || (target.getAttribute("data-dropscope") || "private");
        const folderId = target.getAttribute("data-dropfolder") || "";
        const label = target.getAttribute("data-droplabel") || "";
        if (move && ev.dataTransfer.files.length === 0) {
          if ((move.scope || scope) !== scope) { window.toast(S.noCross); return; }
          return moveDropped(move.id, scope, folderId, label, move.from);
        }
        return uploadDropped(ev.dataTransfer.files, scope, folderId, label);
      }
      // dropped on empty page space: whichever upload form is on screen
      return uploadDropped(ev.dataTransfer.files, visibleScope(), "", "");
    });

    function hasFiles(ev) {
      const types = ev.dataTransfer && ev.dataTransfer.types;
      if (!types) return false;
      return Array.from(types).includes("Files") || hasMove(ev);
    }
    function hasMove(ev) {
      return ev.dataTransfer && Array.from(ev.dataTransfer.types || []).includes(MOVE_MIME);
    }
    function readMove(ev) {
      const raw = ev.dataTransfer.getData(MOVE_MIME);
      if (!raw) return null;
      try { return JSON.parse(raw); } catch { return null; }
    }
    function scopeOf(el) {
      const s = el.getAttribute("data-dropscope");
      return s === "public" || s === "private" ? s : null;
    }
    function dropLabel(el) {
      const label = el.getAttribute("data-droplabel");
      const folder = el.getAttribute("data-dropfolder");
      return label ? fill(S.dropInto, { name: label }) : folder ? S.dropFolder : S.dropUpload;
    }
  }

  ready(() => {
    const drawer = document.getElementById("nav-drawer");
    const toggle = document.getElementById("nav-toggle");
    if (toggle && drawer) toggle.addEventListener("click", () => { drawer.open = !drawer.open; });

    installDragDrop();

    const themeBtn = document.getElementById("theme-toggle");
    if (themeBtn) themeBtn.addEventListener("click", () => {
      const root = document.documentElement;
      const cur = root.classList.contains("mdui-theme-dark") ? "dark"
        : root.classList.contains("mdui-theme-light") ? "light" : "auto";
      const next = cur === "dark" ? "light" : cur === "light" ? "auto" : "dark";
      const names = { dark: S.dark, light: S.light, auto: S.auto };
      root.classList.remove("mdui-theme-auto", "mdui-theme-light", "mdui-theme-dark");
      root.classList.add("mdui-theme-" + next);
      window.toast(S.theme + names[next]);
    });

    // 全域委派：複製 / 預覽（含動態加入的結果列）
    document.addEventListener("click", (ev) => {
      const cp = ev.target && ev.target.closest ? ev.target.closest("[data-copy]") : null;
      if (cp) { copyText(cp.getAttribute("data-copy")); return; }
      const pv = ev.target && ev.target.closest ? ev.target.closest("[data-preview]") : null;
      if (pv) preview(pv.getAttribute("data-preview"), pv.getAttribute("data-name") || "");
    });

    // 上傳 / 建資料夾頁籤（只看同一層的 panel，避免蓋掉巢狀頁籤）
    document.querySelectorAll("[data-tabs]").forEach((tabs) => {
      const root = tabs.parentElement;
      if (!root) return;
      const panels = Array.from(root.children).filter((el) => el.hasAttribute("data-tabpanel"));
      const show = (v) => {
        try { tabs.value = v; } catch {}
        panels.forEach((p) => { p.hidden = p.getAttribute("data-tabpanel") !== v; });
      };
      tabs.querySelectorAll("mdui-tab").forEach((t) =>
        t.addEventListener("click", () => show(t.getAttribute("value"))));
      show(tabs.getAttribute("value") || (tabs.querySelector("mdui-tab") || {}).getAttribute?.("value"));
    });

    // 分段上傳（公開 + 私人共用，data-merge 指向各自合併端點）；可一次選多個檔
    document.querySelectorAll("form[data-chunked]").forEach((form) => {
      form.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const input = form.querySelector('input[type="file"]');
        const files = Array.from((input && input.files) || []);
        if (!files.length) { window.toast(S.needFile); return; }
        for (let i = 0; i < files.length; i++) {
          if (files.length > 1) window.toast(fill(S.multi, { i: i + 1, n: files.length, name: files[i].name }));
          pickFile(input, files[i]);
          await chunkedUpload(form);
        }
        if (files.length > 1) window.location.reload();
      });
    });

    // 並行下載
    document.querySelectorAll("[data-mt-download]").forEach((btn) => {
      btn.addEventListener("click", () => mtDownload(btn));
    });

    // 預覽（靜態列；動態結果列走全域委派）

    // 私人新增資料夾
    document.querySelectorAll("form[data-mkdir]").forEach((form) => {
      form.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const name = fieldValue(form, "name");
        if (!name) { window.toast(S.needName); return; }
        try {
          const res = await fetch("/api/folders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name }),
          });
          if (!res.ok) throw new Error("HTTP " + res.status);
          window.toast(S.mkdirOk);
          window.location.reload();
        } catch { window.toast(S.mkdirFail); }
      });
    });

    // 私人資料夾分享連結：建立 / 取消
    document.querySelectorAll("[data-share-create]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const res = await fetch(`/api/folders/${btn.getAttribute("data-share-create")}/share`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: btn.getAttribute("data-mode") || "view" }),
          });
          if (!res.ok) throw new Error("HTTP " + res.status);
          window.toast(S.shareOk);
          window.location.reload();
        } catch { window.toast(S.mkdirFail); }
      });
    });
    document.querySelectorAll("[data-unshare]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!window.confirm(CONFIRM.unshare[key])) return;
        try {
          const res = await fetch("/api/share/revoke", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: btn.getAttribute("data-unshare") }),
          });
          if (!res.ok) throw new Error("HTTP " + res.status);
          window.toast(S.unshareOk);
          window.location.reload();
        } catch { window.toast(S.unshareFail); }
      });
    });

    // 刪除私人資料夾（含其中的檔案）
    document.querySelectorAll("[data-delete-dir]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const name = btn.getAttribute("data-name") || "";
        const count = btn.getAttribute("data-count") || "0";
        if (window.confirm(folderConfirm(name, count))) {
          window.location.href = btn.getAttribute("data-delete-dir");
        }
      });
    });

    // 刪除公開資料夾（管理員）
    document.querySelectorAll("[data-delpubdir]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const name = btn.getAttribute("data-name") || "";
        const count = btn.getAttribute("data-count") || "0";
        if (window.confirm(pubFolderConfirm(name, count))) {
          window.location.href = btn.getAttribute("data-delpubdir");
        }
      });
    });

    // 刪除確認
    document.querySelectorAll("[data-delete]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const name = btn.getAttribute("data-name") || "";
        if (!window.confirm(fileConfirm(name))) return;
        if (btn.hasAttribute("data-delete-post")) {
          try {
            const res = await fetch(btn.getAttribute("data-delete"), { method: "POST" });
            if (!res.ok) throw new Error("HTTP " + res.status);
            window.toast(S.deleted);
            window.location.reload();
          } catch { window.toast(S.deleteFail); }
          return;
        }
        window.location.href = btn.getAttribute("data-delete");
      });
    });

    // 程式碼區塊複製鈕
    document.querySelectorAll("pre.curl, .mdui-prose pre").forEach((pre) => {
      if (pre.parentElement && pre.parentElement.classList.contains("codeblock")) return;
      const wrap = document.createElement("div");
      wrap.className = "codeblock";
      pre.replaceWith(wrap);
      wrap.appendChild(pre);
      const btn = document.createElement("mdui-button-icon");
      btn.setAttribute("icon", "content_copy");
      btn.setAttribute("title", "複製");
      btn.className = "copybtn";
      btn.addEventListener("click", () => copyText(pre.innerText, "已複製"));
      wrap.appendChild(btn);
    });

    // 檔案排序：時間 / 大小 / 名稱
    document.querySelectorAll("[data-sortbar]").forEach((bar) => {
      const host = bar.closest(".card-pad") || bar.parentElement;
      const list = host ? host.querySelector("mdui-list") : null;
      if (!list) return;
      const btns = bar.querySelectorAll("[data-sort-by]");
      const dirBtn = bar.querySelector("[data-sort-dir]");
      const apply = () => {
        const by = bar.getAttribute("data-by") || "time";
        const desc = (bar.getAttribute("data-dir") || "desc") === "desc";
        const items = Array.from(list.querySelectorAll("mdui-list-item"));
        items.sort((a, b) => {
          let r;
          if (by === "name") {
            const x = a.getAttribute("data-sort-name") || "", y = b.getAttribute("data-sort-name") || "";
            r = x < y ? -1 : x > y ? 1 : 0;
          } else {
            r = parseFloat(a.getAttribute("data-sort-" + by) || "0") - parseFloat(b.getAttribute("data-sort-" + by) || "0");
          }
          return desc ? -r : r;
        });
        items.forEach((el) => list.appendChild(el));
        btns.forEach((b) => b.setAttribute("variant", b.getAttribute("data-sort-by") === by ? "filled" : "text"));
        if (dirBtn) dirBtn.setAttribute("icon", desc ? "arrow_downward" : "arrow_upward");
      };
      btns.forEach((b) => b.addEventListener("click", () => { bar.setAttribute("data-by", b.getAttribute("data-sort-by")); apply(); }));
      if (dirBtn) dirBtn.addEventListener("click", () => {
        bar.setAttribute("data-dir", (bar.getAttribute("data-dir") || "desc") === "desc" ? "asc" : "desc");
        apply();
      });
      apply();
    });

    // 建立資料夾（有結果框就地顯示，否則跳轉）
    document.querySelectorAll("[data-create-folder]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.loading = true;
        try {
          const host = btn.closest(".card-pad") || btn.parentElement;
          const name = host ? fieldValue(host, "mkdir-name") : "";
          const res = await fetch("/api/public/folder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(name ? { name } : {}),
          });
          const data = await res.json();
          const out = host ? host.querySelector("[data-upload-result]") : null;
          if (out) {
            out.innerHTML = resultCard(S.folderCreated, "", data.folder_name || S.idle, [
              linkRow(S.rowLink, data.folder_url,
                `<a href="${esc(data.folder_url)}"><mdui-button variant="text">${esc(S.open)}</mdui-button></a>` +
                `<mdui-button variant="text" data-copy="${esc(data.folder_url)}">${esc(S.copy)}</mdui-button>`),
            ]);
            window.toast(S.folderMade);
          } else {
            window.location.href = data.folder_url;
          }
        } catch { window.toast(S.folderFail); }
        finally { btn.loading = false; }
      });
    });
  });
})();
