// CaveMan Drop 瀏覽器互動：側欄、主題、複製、分段上傳、並行下載、預覽、刪除確認。
// 列表的更新（新增／改名／刪除／移動）全部在 client 即時改 DOM，不 reload。
(function () {
  const THREADS = 16;
  const CHUNK = 4 * 1024 * 1024;
  // 用前幾個 chunk 決定並行數：量到 ADAPT_MS 的實際傳輸、或 ADAPT_CHUNKS 個塊
  const ADAPT_MS = 2000;
  const ADAPT_MAX_MS = 6000;
  const ADAPT_CHUNKS = 6;
  const ADAPT_BYTES = 4 * 1024 * 1024;

  // 語言由瀏覽器偵測（<head> 內腳本寫 lang cookie，見 app/i18n/ui）：server 端 data-lang 就是結果
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
      rowLink: "連結", rowDirect: "直連", rowFolder: "資料夾",
      copy: "複製", open: "開啟", preview: "預覽", close: "關閉",
      download: "下載", directLink: "直接連結", copyLink: "複製連結", delBtn: "刪除",
      items: "{n} 個項目", emptyFiles: "還沒有檔案。",
      zipBtn: "打包下載", shareView: "檢視連結",
      dropUpload: "放開手上傳", dropInto: "放到「{name}」", dropFolder: "放到這個資料夾",
      multi: "上傳 {i}/{n}：{name}", previewTitle: "預覽 — ",
      rename: "改名", renameOk: "已改名", renameFail: "改名失敗", newFolder: "新增資料夾",
      save: "儲存", cancel: "取消", nameLabel: "名稱", driveTitle: "我的雲端",
      urlNeed: "請先輸入檔案網址", urlFail: "從網址上傳失敗：", urlUp: "從網址上傳",
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
      rowLink: "Link", rowDirect: "Direct", rowFolder: "Folder",
      copy: "Copy", open: "Open", preview: "Preview", close: "Close",
      download: "Download", directLink: "Direct link", copyLink: "Copy link", delBtn: "Delete",
      items: "{n} items", emptyFiles: "No files yet.",
      zipBtn: "Download .zip", shareView: "View link",
      dropUpload: "Drop to upload", dropInto: "Drop into “{name}”", dropFolder: "Drop into this folder",
      multi: "Uploading {i}/{n}: {name}", previewTitle: "Preview — ",
      rename: "Rename", renameOk: "Renamed", renameFail: "Rename failed", newFolder: "New folder",
      save: "Save", cancel: "Cancel", nameLabel: "Name", driveTitle: "My drive",
      urlNeed: "Enter a file URL first", urlFail: "URL upload failed: ", urlUp: "URL upload",
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

  // ---- 列列更新的小工具（新檔案／資料夾列就這樣蓋出來，跟 ui.py 一模一樣）----
  function fmtTime(ts) {
    const d = new Date(Number(ts) * 1000);
    if (!Number(ts) || isNaN(d.getTime())) return "";
    const p = (x) => String(x).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  function metaLine(f, withType) {
    const bits = [fmtMB(f.bytes != null ? f.bytes : f.size || 0)];
    if (withType && f.content_type) bits.push(f.content_type);
    const t2 = fmtTime(f.ctime);
    if (t2) bits.push(t2);
    if (f.description) bits.push(f.description);
    return bits.join(" · ");
  }

  function fileRowHtml(f) {
    const pub = f.scope === "public";
    const dl = f.dl
      || (pub ? (f.folder_id ? `/dl/pub/${f.folder_id}/${f.id}` : `/dl/s/${f.id}`) : `/dl/${f.id}`);
    const pv = pub ? dl + "?preview=1" : `/view/${f.id}`;
    const copyTarget = pub && f.short_url ? f.short_url : dl;
    const copyLabel = pub ? S.copyLink : S.directLink;
    const delUrl = pub ? `/delpub/${f.id}` : `/del/${f.id}`;
    return (
      `<mdui-list-item draggable="true" data-move="${esc(f.id)}"` +
      ` data-scope="${pub ? "public" : "private"}" data-from="${esc(f.folder_id || "")}"` +
      ` data-name="${esc(f.name)}" data-sort-name="${esc(String(f.name).toLowerCase())}"` +
      ` data-sort-size="${esc(String(f.bytes || 0))}" data-sort-time="${esc(String(f.ctime || 0))}">` +
      '<mdui-icon slot="icon" name="description"></mdui-icon>' +
      `<div><div class="fname">${esc(f.name)}</div>` +
      `<div class="fmeta">${esc(metaLine(f, !pub))}</div></div>` +
      `<mdui-button-icon slot="end-icon" icon="visibility" data-preview="${esc(pv)}"` +
      ` data-name="${esc(f.name)}" title="${esc(S.preview)}"></mdui-button-icon>` +
      `<mdui-button-icon slot="end-icon" icon="download" data-mt-download="${esc(dl)}"` +
      ` data-name="${esc(f.name)}" data-size="${esc(String(f.bytes || 0))}"` +
      ` title="${esc(S.download)}"></mdui-button-icon>` +
      `<mdui-button slot="end-icon" variant="text" data-copy="${esc(copyTarget)}">${esc(copyLabel)}</mdui-button>` +
      `<mdui-button-icon slot="end-icon" icon="edit" data-rename-file="${esc(f.id)}"` +
      ` data-name="${esc(f.name)}" data-public="${pub ? 1 : 0}"` +
      ` data-in-folder="${esc(f.folder_id || "")}" title="${esc(S.rename)}"></mdui-button-icon>` +
      `<mdui-button slot="end-icon" variant="text" data-delete="${esc(delUrl)}"` +
      ` data-delete-post="1" data-name="${esc(f.name)}">${esc(S.delBtn)}</mdui-button>` +
      "</mdui-list-item>"
    );
  }

  function folderRowHtml(fid, name, count, ctime, isPublic) {
    const href = isPublic ? `/f/${fid}` : `/?folder=${fid}`;
    const zipHref = isPublic ? `/zip/f/${fid}` : `/zip/${fid}`;
    let btns;
    if (isPublic) {
      btns = (
        `<a href="${esc(href)}"><mdui-button-icon icon="open_in_new" title="${esc(S.open)}"></mdui-button-icon></a>` +
        `<mdui-button-icon icon="archive" title="${esc(S.zipBtn)}" data-zip="${esc(zipHref)}"></mdui-button-icon>` +
        `<mdui-button-icon icon="edit" data-rename="${esc(fid)}" data-name="${esc(name)}"` +
        ` data-public="1" title="${esc(S.rename)}"></mdui-button-icon>` +
        `<mdui-button-icon icon="delete" data-delpubdir="${esc(`/delpubdir/${fid}`)}"` +
        ` data-name="${esc(name)}" data-count="${count}" title="${esc(S.delBtn)}"></mdui-button-icon>`
      );
    } else {
      btns = (
        `<mdui-button-icon icon="folder_open" data-open="${esc(href)}" title="${esc(S.open)}"></mdui-button-icon>` +
        `<mdui-button-icon icon="archive" title="${esc(S.zipBtn)}" data-zip="${esc(zipHref)}"></mdui-button-icon>` +
        `<mdui-button-icon icon="link" data-share-create="${esc(fid)}" data-mode="view"` +
        ` title="${esc(S.shareView)}"></mdui-button-icon>` +
        `<mdui-button-icon icon="edit" data-rename="${esc(fid)}" data-name="${esc(name)}"` +
        ` data-public="0" title="${esc(S.rename)}"></mdui-button-icon>` +
        `<mdui-button-icon icon="delete" data-delete-dir="${esc(`/deldir/${fid}`)}"` +
        ` data-name="${esc(name)}" data-count="${count}" title="${esc(S.delBtn)}"></mdui-button-icon>`
      );
    }
    return (
      `<mdui-list-item class="frow" data-dropscope="${isPublic ? "public" : "private"}"` +
      ` data-dropfolder="${esc(fid)}" data-droplabel="${esc(name)}" data-count="${count}"` +
      ` data-sort-name="${esc(String(name).toLowerCase())}" data-sort-time="${esc(String(ctime || 0))}"` +
      ' data-sort-size="0">' +
      '<mdui-icon slot="icon" name="folder"></mdui-icon>' +
      `<div><a class="fname" href="${esc(href)}">${esc(name)}</a>` +
      `<div class="fmeta">${esc(fill(S.items, { n: count }))}</div></div>` +
      `<span slot="end-icon" class="frow-btns">${btns}</span>` +
      "</mdui-list-item>"
    );
  }

  // 目前看得到的那張列表卡（公開資料夾頁、雲端分頁都各自一張）
  function visibleCard() {
    const cards = Array.from(document.querySelectorAll(".card-pad")).filter((c) => c.offsetParent !== null);
    return cards.find((c) => c.querySelector("[data-sortbar]") || c.querySelector("mdui-list.file-list")) || null;
  }
  function ensureFileList(card) {
    if (!card) return null;
    let list = card.querySelector("mdui-list.file-list");
    if (list) return list;
    const empty = card.querySelector("mdui-card.empty");
    if (empty) empty.remove();
    list = document.createElement("mdui-list");
    list.className = "file-list";
    const sortbar = card.querySelector("[data-sortbar]");
    if (sortbar) sortbar.insertAdjacentElement("afterend", list);
    else card.appendChild(list);
    return list;
  }
  function updateHeadCount(card, by) {
    if (!card || !by) return;
    const h = card.querySelector(".drive-head h2");
    if (!h) return;
    const m = h.textContent.match(/^(.*?)([（(])(\d+)([）)])\s*$/);
    if (!m) return;
    h.textContent = m[1] + m[2] + Math.max(0, parseInt(m[3], 10) + by) + m[4];
  }
  function adjustFolderCount(scope, fid, by) {
    if (!fid) return;
    const card = visibleCard();
    const row = card && card.querySelector(`mdui-list-item.frow[data-dropscope="${scope}"][data-dropfolder="${CSS.escape(fid)}"]`);
    if (!row) return;
    const n = Math.max(0, parseInt(row.getAttribute("data-count") || "0", 10) + by);
    row.setAttribute("data-count", String(n));
    const meta = row.querySelector(".fmeta");
    if (meta) meta.textContent = fill(S.items, { n });
    const del = row.querySelector("[data-count]");
    if (del) del.setAttribute("data-count", String(n));
  }
  function insertRow(html, bump) {
    const card = visibleCard();
    const list = ensureFileList(card);
    if (!list) return;
    list.insertAdjacentHTML("afterbegin", html);
    updateHeadCount(card, bump == null ? 1 : bump);
  }
  function afterRowGone(row) {
    const card = row.closest(".card-pad");
    const list = row.closest("mdui-list.file-list");
    row.remove();
    updateHeadCount(card, -1);
    if (list && !list.children.length) {
      list.remove();
      const mark = document.createElement("mdui-card");
      mark.setAttribute("variant", "filled");
      mark.className = "empty";
      mark.textContent = S.emptyFiles;
      card.appendChild(mark);
    }
  }

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
  async function chunkedUpload(form, theFile) {
    const file = theFile || (function () {
      for (const inp of form.querySelectorAll('input[type="file"]')) {
        if (inp.files && inp.files[0]) return inp.files[0];
      }
      return null;
    })();
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
    if (pauseBtn) { pauseBtn.textContent = S.pause; }
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
      const secs = elapsed < 10 ? elapsed.toFixed(1) : Math.round(elapsed);
      const stats = fill(S.stats, {
        size: fmtMB(data.size_bytes), secs, rate: fmtMB(data.size_bytes / elapsed),
        dup: data.deduplicated ? S.dup : "",
      });
      if (isPublic) {
        const out = form.parentElement.querySelector("[data-upload-result]");
        const durl = data.download_url || data.url;
        const furl = data.folder_url || data.share_url;
        const share = data.short_url || durl;   // catbox-style short link when we have one
        // 上傳完成不給「開啟」鈕：只留預覽／複製
        const rows = [];
        if (share && share !== durl) {
          rows.push(linkRow(S.rowLink, share,
            `<mdui-button variant="text" data-copy="${esc(share)}">${esc(S.copy)}</mdui-button>`));
        }
        rows.push(linkRow(S.rowDirect, durl,
          `<mdui-button variant="text" data-preview="${esc(durl)}?preview=1" data-name="${esc(data.filename)}">${esc(S.preview)}</mdui-button>` +
          `<mdui-button variant="text" data-copy="${esc(durl)}">${esc(S.copy)}</mdui-button>`));
        if (furl) {
          rows.push(linkRow(S.rowFolder, furl,
            `<mdui-button variant="text" data-copy="${esc(furl)}">${esc(S.copy)}</mdui-button>`));
        }
        const html = resultCard(S.upDone, data.filename, stats, rows);
        if (out) out.innerHTML = html;
        if (panel) panel.hidden = true;
        // 就地把新檔塞進目前看得到的列表
        insertRow(fileRowHtml({
          id: data.file_id, name: data.filename, bytes: data.size_bytes,
          ctime: Date.now() / 1000, description: data.description,
          scope: "public", folder_id: data.folder_id, short_url: data.short_url,
        }));
        window.toast(S.done);
      } else {
        if (panel) panel.hidden = true;
        insertRow(fileRowHtml({
          id: data.file_id, name: file.name, bytes: data.size_bytes,
          ctime: Date.now() / 1000, description: data.description || desc,
          scope: "private", folder_id: fieldValue(form, "folder_id"),
        }));
        window.toast(S.done);
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

  // ---- 改名／新增資料夾：同一個輸入對話框 ----
  function askName(headline, value) {
    return new Promise((resolve) => {
      const dlg = document.createElement("mdui-dialog");
      dlg.setAttribute("headline", headline);
      dlg.innerHTML = `<mdui-text-field label="${esc(S.nameLabel)}" value="${esc(value || "")}"
          variant="filled" data-namefield></mdui-text-field>
        <mdui-button slot="action" variant="text" data-no>${esc(S.cancel)}</mdui-button>
        <mdui-button slot="action" variant="filled" data-yes>${esc(S.save)}</mdui-button>`;
      document.body.appendChild(dlg);
      const field = dlg.querySelector("[data-namefield]");
      let settled = false;
      const done = (val) => {
        if (settled) return;
        settled = true;
        dlg.open = false;
        setTimeout(() => dlg.remove(), 300);
        resolve(val);
      };
      dlg.querySelector("[data-no]").addEventListener("click", () => done(null));
      dlg.querySelector("[data-yes]").addEventListener("click", () => done(String(field.value || "").trim() || null));
      field.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") { ev.preventDefault(); done(String(field.value || "").trim() || null); }
      });
      dlg.addEventListener("closed", () => done(null));   // Esc / overlay = cancel
      dlg.open = true;
      setTimeout(() => { try { field.focus(); } catch { /* focus 是選的 */ } }, 60);
    });
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    return res.json().catch(() => ({}));
  }

  // ---- 拖放：拖檔案進資料夾、拖檔案列換資料夾、整頁拖放上傳 ----
  function formForScope(scope) {
    const forms = Array.from(document.querySelectorAll("form[data-chunked]"))
      .filter((f) => f.offsetParent !== null);   // visible tab only
    return forms.find((f) => (scope === "public") === f.hasAttribute("data-public")) || null;
  }

  // The private drive's uploader already carries the folder being viewed, so a
  // drop on empty page space keeps that folder. `null` means "leave it as is".
  function dropContext() {
    const panel = Array.from(document.querySelectorAll("[data-tabpanel]")).find((p) => !p.hidden);
    const form = panel && panel.querySelector("form[data-chunked]");
    if (!form) return { scope: "private", form: null, folderId: null };
    if (form.hasAttribute("data-public")) return { scope: "public", form, folderId: "" };
    return { scope: "private", form, folderId: null };
  }

  function setTargetFolder(form, scope, folderId) {
    if (folderId === null) return;               // keep whatever the form says
    if (scope === "public") {
      const field = form.querySelector('[name="folder"]');
      if (field) field.value = folderId;
      return;
    }
    const sel = form.querySelector('[name="folder_id"]');
    if (sel) sel.value = folderId || "";
  }

  async function uploadDropped(files, scope, folderId, label) {
    const form = formForScope(scope);
    if (!form) { window.toast(S.switchTab); return; }
    setTargetFolder(form, scope, folderId);
    const list = Array.from(files);
    for (let i = 0; i < list.length; i++) {
      if (list.length > 1) window.toast(fill(S.multi, { i: i + 1, n: list.length, name: list[i].name }));
      await chunkedUpload(form, list[i]);
    }
    if (label) window.toast(S.uploadedTo + label);
  }

  function adjustCountsForVisualMove(row, scope, targetFolder) {
    const from = row.getAttribute("data-from") || "";
    const to = targetFolder || "";
    if (from === to) return;
    // 資料夾列上的項目計數跟著動
    adjustFolderCount(scope, from, -1);
    adjustFolderCount(scope, to, +1);
    if (scope === "private") {
      // 私人雲端一次只顯示一個資料夾：移去别的資料夾就把列拿掉
      const panelForm = formForScope("private");
      const viewed = panelForm ? fieldValue(panelForm, "folder_id") : "";
      if ((from || "") === (viewed || "") && to !== (viewed || "")) afterRowGone(row);
      else row.setAttribute("data-from", to);
    } else {
      // 公開分頁列出所有公開檔：留下列，只更新所屬資料夾
      row.setAttribute("data-from", to);
    }
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
      // 即時更新列與資料夾計數，不 reload
      const row = document.querySelector(`mdui-list-item[data-move="${CSS.escape(fileId)}"]`);
      if (row) adjustCountsForVisualMove(row, scope, folderId);
      window.toast(label ? S.moved + label : S.movedOut);
    } catch { window.toast(S.moveFail); }
  }

  // ---- URL 上傳：伺服器經 proxy 抓回來當公開上傳 ----
  async function uploadFromUrl(btn) {
    const host = btn.closest(".card-pad") || btn.parentElement;
    if (!host) return;
    const urlField = host.querySelector("[data-url-input]")
      || (host.parentElement && host.parentElement.querySelector("[data-url-input]"));
    if (!urlField) return;
    const inner = urlField.querySelector ? urlField.querySelector("input") : null;
    const url = String(urlField.value != null && urlField.value !== "" ? urlField.value : inner ? inner.value : "").trim();
    if (!url) { window.toast(S.urlNeed); return; }
    const form = host.querySelector("form[data-chunked]");
    const folder = form ? fieldValue(form, "folder") : "";
    const desc = form ? fieldValue(form, "description") : "";
    btn.loading = true;
    try {
      const res = await fetch("/api/public/upload_url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, folder: folder || null, description: desc }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
      const durl = data.download_url || data.url;
      const furl = data.folder_url || data.share_url;
      const share = data.short_url || durl;
      const rows = [];
      if (share && share !== durl) {
        rows.push(linkRow(S.rowLink, share,
          `<mdui-button variant="text" data-copy="${esc(share)}">${esc(S.copy)}</mdui-button>`));
      }
      rows.push(linkRow(S.rowDirect, durl,
        `<mdui-button variant="text" data-preview="${esc(durl)}?preview=1" data-name="${esc(data.filename)}">${esc(S.preview)}</mdui-button>` +
        `<mdui-button variant="text" data-copy="${esc(durl)}">${esc(S.copy)}</mdui-button>`));
      if (furl) {
        rows.push(linkRow(S.rowFolder, furl,
          `<mdui-button variant="text" data-copy="${esc(furl)}">${esc(S.copy)}</mdui-button>`));
      }
      const out = host.querySelector("[data-upload-result]");
      if (out) out.innerHTML = resultCard(S.upDone, data.filename, "", rows);
      window.toast(S.done);
      // 就地插入列（公開資料夾頁／公開分頁），找到資料夾時伺服器回 folder_id
      insertRow(fileRowHtml({
        id: data.file_id, name: data.filename, bytes: data.size_bytes,
        ctime: Date.now() / 1000, description: data.description,
        scope: "public", folder_id: data.folder_id, short_url: data.short_url,
      }));
    } catch (err) {
      window.toast(S.urlFail + err.message);
    } finally { btn.loading = false; }
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
      ev.dataTransfer.dropEffect = "copy";
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
      // dropped on empty page space: the uploader that is on screen, into the
      // folder the drive is currently showing
      const ctx = dropContext();
      return uploadDropped(ev.dataTransfer.files, ctx.scope, ctx.folderId, "");
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

    // 上傳表單：data-dirpick 時走整個資料夾的 input（webkitdirectory）
    document.querySelectorAll("form[data-chunked]").forEach((form) => {
      form.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        let files;
        if (form.dataset.dirpick === "1") {
          const dIn = form.querySelector('input[name="dir_files"]');
          files = Array.from((dIn && dIn.files) || []);
          delete form.dataset.dirpick;
        } else {
          const input = form.querySelector('input[name="file"]');
          files = Array.from((input && input.files) || []);
        }
        if (!files.length) { window.toast(S.needFile); return; }
        for (let i = 0; i < files.length; i++) {
          if (files.length > 1) window.toast(fill(S.multi, { i: i + 1, n: files.length, name: files[i].name }));
          await chunkedUpload(form, files[i]);
        }
      });
    });

    // 雲端工具列與公開表單：選整個資料夾（dir input）→ 打開挑選器
    document.querySelectorAll("[data-dir-pick], [data-drive-dir]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const form = btn.closest("form[data-chunked]")
          || (btn.closest("[data-tabpanel]") || document).querySelector("form[data-chunked]:not([data-public])")
          || document.querySelector("form.drive-upload");
        if (!form) return;
        const dirIn = form.querySelector('input[name="dir_files"]');
        if (!dirIn) return;
        form.dataset.dirpick = "1";
        dirIn.click();
      });
    });
    // 挑完檔直接送出表單（含 dir picker、取消時不送）
    document.querySelectorAll("form[data-chunked] input[type=file]").forEach((input) => {
      input.addEventListener("change", () => {
        if (input.files && input.files.length && input.form) input.form.requestSubmit();
      });
    });

    // 雲端工具列：上傳（隱藏的 input 打開選擇器）
    document.querySelectorAll("[data-drive-upload]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const panel = btn.closest("[data-tabpanel]") || document;
        const input = panel.querySelector('form[data-chunked]:not([data-public]) input[name="file"]')
          || document.querySelector('form[data-chunked]:not([data-public]) input[name="file"]');
        if (input) input.click();
      });
    });

    // 雲端工具列：新增資料夾 → 就地插入列，不 reload
    document.querySelectorAll("[data-new-folder]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const name = await askName(S.newFolder, "");
        if (!name) return;
        try {
          const data = await postJSON("/api/folders", { name });
          insertRow(folderRowHtml(data.folder_id, data.name || name, 0, Date.now() / 1000, false));
          window.toast(S.mkdirOk);
        } catch { window.toast(S.mkdirFail); }
      });
    });

    // 公開「建立資料夾」：建好直接開資料夾頁
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
          if (!res.ok) throw new Error(data.detail || "x");
          window.location.href = data.folder_url;   // 開啟資料夾頁（不留在原頁）
        } catch { window.toast(S.folderFail); }
        finally { btn.loading = false; }
      });
    });

    // 從網址上傳
    document.querySelectorAll("[data-url-upload]").forEach((btn) => {
      btn.addEventListener("click", () => uploadFromUrl(btn));
    });

    // 全域委派：複製 / 預覽 / 打包 zip / 開資料夾 / 改名 / 分享 / 刪除
    // （列是動態插入的，統一委派才不會漏）
    document.addEventListener("click", async (ev) => {
      const hit = (sel) => ev.target && ev.target.closest ? ev.target.closest(sel) : null;
      const cp = hit("[data-copy]");
      if (cp) { copyText(cp.getAttribute("data-copy")); return; }
      const pv = hit("[data-preview]");
      if (pv) { preview(pv.getAttribute("data-preview"), pv.getAttribute("data-name") || ""); return; }
      const zip = hit("[data-zip]");
      if (zip) { window.location.href = zip.getAttribute("data-zip"); return; }
      const opener = hit("[data-open]");
      if (opener) { ev.preventDefault(); ev.stopPropagation(); window.location.href = opener.getAttribute("data-open"); return; }

      // 改名：資料夾
      const rn = hit("[data-rename]");
      if (rn) {
        ev.preventDefault(); ev.stopPropagation();
        const id = rn.getAttribute("data-rename");
        const isPublic = rn.getAttribute("data-public") === "1";
        const name = await askName(S.rename, rn.getAttribute("data-name") || "");
        if (!name) return;
        try {
          await postJSON(isPublic ? "/api/public/folder/rename" : "/api/folders/rename",
            { folder_id: id, name });
          const row = rn.closest("mdui-list-item.frow");
          if (row) {
            row.setAttribute("data-name", name);
            row.setAttribute("data-droplabel", name);
            row.setAttribute("data-sort-name", String(name).toLowerCase());
            const fname = row.querySelector("a.fname, .fname");
            if (fname) fname.textContent = name;
            const dl = row.querySelector("[data-name]");
            if (dl) dl.setAttribute("data-name", name);
          }
          window.toast(S.renameOk);
        } catch { window.toast(S.renameFail); }
        return;
      }

      // 改名：檔案
      const rn2 = hit("[data-rename-file]");
      if (rn2) {
        ev.preventDefault(); ev.stopPropagation();
        const name2 = await askName(S.rename, rn2.getAttribute("data-name") || "");
        if (!name2) return;
        try {
          await postJSON(rn2.getAttribute("data-public") === "1"
            ? "/api/public/file/rename" : "/api/files/rename",
            { file_id: rn2.getAttribute("data-rename-file"), name: name2,
              folder_id: rn2.getAttribute("data-in-folder") || null });
          const row = rn2.closest("mdui-list-item");
          if (row) {
            row.setAttribute("data-name", name2);
            row.setAttribute("data-sort-name", String(name2).toLowerCase());
            const fname = row.querySelector(".fname");
            if (fname) fname.textContent = name2;
            row.querySelectorAll("[data-name]").forEach((b) => b.setAttribute("data-name", name2));
          }
          window.toast(S.renameOk);
        } catch { window.toast(S.renameFail); }
        return;
      }

      // 分享（無列變化，只提示）
      const sc = hit("[data-share-create]");
      if (sc) {
        try {
          const res = await fetch(`/api/folders/${sc.getAttribute("data-share-create")}/share`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: sc.getAttribute("data-mode") || "view" }),
          });
          if (!res.ok) throw new Error("HTTP " + res.status);
          window.toast(S.shareOk);
        } catch { window.toast(S.mkdirFail); }
        return;
      }
      const un = hit("[data-unshare]");
      if (un) {
        if (!window.confirm(CONFIRM.unshare[key])) return;
        try {
          const res = await fetch("/api/share/revoke", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: un.getAttribute("data-unshare") }),
          });
          if (!res.ok) throw new Error("HTTP " + res.status);
          window.toast(S.unshareOk);
          window.location.reload();
        } catch { window.toast(S.unshareFail); }
        return;
      }

      // 刪除資料夾（私有／公開）
      const ddir = hit("[data-delete-dir], [data-delpubdir]");
      if (ddir) {
        ev.preventDefault(); ev.stopPropagation();
        const name = ddir.getAttribute("data-name") || "";
        const count = ddir.getAttribute("data-count") || "0";
        const isPub = ddir.hasAttribute("data-delpubdir");
        if (!window.confirm(isPub ? pubFolderConfirm(name, count) : folderConfirm(name, count))) return;
        try {
          const res = await fetch(ddir.getAttribute(isPub ? "data-delpubdir" : "data-delete-dir"), { method: "POST" });
          if (!res.ok) throw new Error("HTTP " + res.status);
          const row = ddir.closest("mdui-list-item.frow");
          if (row) {
            const card = row.closest(".card-pad");
            const list = row.closest("mdui-list.file-list");
            row.remove();
            updateHeadCount(card, -1);
            if (list && !list.children.length) {
              list.remove();
              const mark = document.createElement("mdui-card");
              mark.setAttribute("variant", "filled");
              mark.className = "empty";
              mark.textContent = S.emptyFiles;
              card.appendChild(mark);
            }
          }
          window.toast(S.deleted);
        } catch { window.toast(S.deleteFail); }
        return;
      }

      // 刪除檔案
      const del = hit("[data-delete]");
      if (del) {
        const name = del.getAttribute("data-name") || "";
        if (!window.confirm(fileConfirm(name))) return;
        if (del.hasAttribute("data-delete-post")) {
          try {
            const res = await fetch(del.getAttribute("data-delete"), { method: "POST" });
            if (!res.ok) throw new Error("HTTP " + res.status);
            const row = del.closest("mdui-list-item");
            if (row) {
              const scope = row.getAttribute("data-scope") || "private";
              const from = row.getAttribute("data-from") || "";
              afterRowGone(row);
              if (from) adjustFolderCount(scope, from, -1);
            }
            window.toast(S.deleted);
          } catch { window.toast(S.deleteFail); }
          return;
        }
        window.location.href = del.getAttribute("data-delete");
        return;
      }

      // 並行下載
      const mtb = hit("[data-mt-download]");
      if (mtb) { mtDownload(mtb); return; }

      // 點資料夾列本身（不是鈕）→ 開資料夾
      const frow = hit("mdui-list-item.frow");
      if (frow && !ev.target.closest("mdui-button, mdui-button-icon, a, input")) {
        const link = frow.querySelector("a.fname");
        if (link) window.location.href = link.getAttribute("href");
      }
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

    // 檔案排序：時間 / 大小 / 名稱。資料夾（.frow）永遠排最前面。
    document.querySelectorAll("[data-sortbar]").forEach((bar) => {
      const host = bar.closest(".card-pad") || bar.parentElement;
      const list = host ? host.querySelector("mdui-list") : null;
      if (!list) return;
      const btns = bar.querySelectorAll("[data-sort-by]");
      const dirBtn = bar.querySelector("[data-sort-dir]");
      const cmp = (a, b) => {
        const by = bar.getAttribute("data-by") || "time";
        if (by === "name") {
          const x = a.getAttribute("data-sort-name") || "", y = b.getAttribute("data-sort-name") || "";
          return x < y ? -1 : x > y ? 1 : 0;
        }
        return parseFloat(a.getAttribute("data-sort-" + by) || "0") - parseFloat(b.getAttribute("data-sort-" + by) || "0");
      };
      const apply = () => {
        const by = bar.getAttribute("data-by") || "time";
        const desc = (bar.getAttribute("data-dir") || "desc") === "desc";
        const items = Array.from(list.querySelectorAll("mdui-list-item"));
        const folders = items.filter((el) => el.classList.contains("frow"));
        const files = items.filter((el) => !el.classList.contains("frow"));
        const wrap = desc ? -1 : 1;
        folders.sort((a, b) => wrap * cmp(a, b));
        files.sort((a, b) => wrap * cmp(a, b));
        folders.forEach((el) => list.appendChild(el));
        files.forEach((el) => list.appendChild(el));
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
  });
})();
