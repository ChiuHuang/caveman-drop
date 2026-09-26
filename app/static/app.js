// CaveMan Drop 瀏覽器互動：側欄、主題、複製、分段上傳、並行下載、預覽、刪除確認。
(function () {
  const THREADS = 16;
  const CHUNK = 4 * 1024 * 1024;

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
      window.toast(okMsg || "連結已複製");
    } catch { window.toast("複製失敗"); }
  }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function fmtMB(n) {
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
    if (n < 1073741824) return (n / 1048576).toFixed(1) + " MB";
    return (n / 1073741824).toFixed(2) + " GB";
  }

  // ---- 分段上傳（含線程表 + 分段條 + 測速 + 暫停）----
  async function chunkedUpload(form) {
    const input = form.querySelector('input[type="file"]');
    const file = input && input.files[0];
    if (!file) { window.toast("請先選擇檔案"); return; }
    const mergeUrl = form.getAttribute("data-merge");
    const isPublic = form.hasAttribute("data-public");
    const folderInput = form.querySelector('[name="folder"]');
    const folderIdInput = form.querySelector('[name="folder_id"]');
    const tokenInput = form.querySelector('[name="token"]');
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
    // 慢連線加線程：先打 1MB 探針，伺服器按真實 IP 記檔位
    let threads = Math.min(THREADS, total);
    const probeUrl = form.getAttribute("data-probe");
    if (probeUrl && total > 4) {
      try {
        const pfd = new FormData();
        pfd.append("probe", new Blob([new Uint8Array(1024 * 1024)]), "probe.bin");
        const pr = await fetch(probeUrl, { method: "POST", body: pfd });
        if (pr.ok) {
          const pj = await pr.json();
          if (pj.threads) threads = Math.max(1, Math.min(128, pj.threads | 0, total));
        }
      } catch { /* 探針失敗就用預設 */ }
    }
    const state = {
      next: 0, done: 0, doneBytes: 0, failed: null,
      paused: false, cancelled: false, threads,
    };

    if (btn) btn.loading = true;
    if (panel) panel.hidden = false;

    // 線程表：最多顯示 16 列，人多時輪流顯示
    const shown = Math.min(state.threads, 16);
    const rowEls = [];
    if (rowsBox) {
      rowsBox.innerHTML = "";
      for (let t = 0; t < shown; t++) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${t + 1}</td><td class="st idle">待命中</td>`;
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
    if (segCount) segCount.textContent = `${total} 塊 / ${NCELL} 格` + (state.threads > 16 ? ` · ${state.threads} 線程` : "");
    const setRow = (t, txt, cls) => {
      const el = rowEls.length ? rowEls[t % rowEls.length] : null;
      if (!el) return;
      el.textContent = txt;
      el.className = "st " + cls;
    };
    const render = () => {
      if (pct) pct.textContent = Math.floor((state.done / total) * 100) + "%";
      if (bar) bar.value = state.done / total;
    };
    render();

    // 測速：每 0.5 秒結算，動畫跟著速度走
    let lastBytes = 0;
    const speedTimer = setInterval(() => {
      const v = (state.doneBytes - lastBytes) * 2;
      lastBytes = state.doneBytes;
      if (speed) speed.textContent = state.done >= total ? "完成" : `${fmtMB(v)}/s · ${state.done}/${total} 塊`;
      if (panel) {
        const mbs = v / 1048576;
        panel.style.setProperty("--pulse-dur", mbs > 50 ? ".3s" : mbs > 10 ? ".6s" : mbs > 0.5 ? "1.2s" : "2s");
      }
    }, 500);
    if (pauseBtn) pauseBtn.addEventListener("click", () => {
      state.paused = !state.paused;
      pauseBtn.textContent = state.paused ? "繼續" : "暫停";
      if (panel) panel.classList.toggle("paused", state.paused);
      window.toast(state.paused ? "已暫停" : "繼續上傳");
    });

    async function worker(t) {
      while (true) {
        if (state.failed || state.cancelled) return;
        while (state.paused && !state.failed) await sleep(200);
        if (state.next >= total) { setRow(t, "待命中", "idle"); return; }
        const i = state.next++;
        setRow(t, `上傳中 #${i + 1}`, "live");
        const cell = cellOf(i);
        if (cellEls[cell]) cellEls[cell].classList.add("active");
        const fd = new FormData();
        fd.append("file_chunk", file.slice(i * CHUNK, (i + 1) * CHUNK), "chunk");
        fd.append("upload_id", uploadId);
        fd.append("index", String(i));
        fd.append("filename", file.name);
        try {
          const res = await fetch(form.action, { method: "POST", body: fd });
          if (!res.ok) throw new Error("HTTP " + res.status);
          try {
            const js = await res.json();
            if (js && js.throttled && note) {
              note.textContent = `分享頻寬限速中（約 ${js.throttle_mbps || 90} Mbps），上傳繼續`;
              if (panel) panel.classList.add("throttled");
            }
          } catch { /* 非 JSON 回應就忽略 */ }
        } catch (err) { state.failed = err; setRow(t, "失敗", "err"); return; }
        state.done++;
        state.doneBytes += Math.min(CHUNK, file.size - i * CHUNK);
        cellGot[cell]++;
        if (cellGot[cell] >= cellNeed[cell] && cellEls[cell]) {
          cellEls[cell].classList.remove("active");
          cellEls[cell].classList.add("done");
        }
        setRow(t, `完成 #${i + 1}`, "ok");
        render();
      }
    }

    await Promise.all(Array.from({ length: state.threads }, (_, t) => worker(t)));
    clearInterval(speedTimer);
    if (state.failed) {
      window.toast("上傳失敗：" + state.failed.message);
      if (btn) btn.loading = false;
      return;
    }
    if (pct) pct.textContent = "合併中…";
    try {
      const body = { upload_id: uploadId, filename: file.name, total_chunks: total };
      if (isPublic && folderInput && folderInput.value.trim()) body.folder = folderInput.value.trim();
      if (!isPublic && folderIdInput && folderIdInput.value) body.folder_id = folderIdInput.value;
      if (tokenInput && tokenInput.value) body.token = tokenInput.value;
      const res = await fetch(mergeUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
      if (btn) btn.loading = false;
      if (isPublic) {
        const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
        const out = form.parentElement.querySelector("[data-upload-result]");
        const durl = data.download_url || data.url;
        const furl = data.folder_url || data.share_url;
        let html = `<mdui-card variant="filled" class="card-pad result-box">
          <div><strong>已上傳：</strong> ${esc(data.filename)} (${fmtMB(data.size_bytes)})</div>
          <div class="rlink"><code>${esc(durl)}</code><span class="rlink-btns">` +
          (furl ? "" : `<mdui-button variant="text" data-preview="${esc(durl)}?preview=1" data-name="${esc(data.filename)}">預覽</mdui-button>`) +
          `<mdui-button variant="text" data-copy="${esc(durl)}">複製</mdui-button></span></div>`;
        if (furl) {
          html += `<div class="rlink"><span class="rlink-label">資料夾</span><code>${esc(furl)}</code><span class="rlink-btns">` +
            `<a href="${esc(furl)}"><mdui-button variant="text">開啟</mdui-button></a>` +
            `<mdui-button variant="text" data-copy="${esc(furl)}">複製</mdui-button></span></div>`;
        }
        html += `</mdui-card>`;
        if (out) out.innerHTML = html;
        if (panel) panel.hidden = true;
        window.toast("上傳完成");
      } else {
        window.toast("上傳完成");
        window.location.reload();
      }
    } catch (err) {
      window.toast("合併失敗：" + err.message);
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
      window.toast(`下載中… ${name}`);
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
      window.toast("下載完成");
    } catch (err) {
      window.toast("下載失敗，改用直接下載");
      window.location.href = url;
    } finally { btn.loading = false; }
  }

  // ---- 預覽：對話框內嵌 iframe ----
  function preview(url, name) {
    const dlg = document.createElement("mdui-dialog");
    dlg.setAttribute("headline", "預覽 — " + name);
    dlg.innerHTML = `<iframe src="${url}" style="width:100%;height:60vh;border:0;border-radius:8px" title="preview"></iframe>
      <mdui-button slot="action" variant="text">關閉</mdui-button>`;
    document.body.appendChild(dlg);
    dlg.querySelector("mdui-button").addEventListener("click", () => { dlg.open = false; setTimeout(() => dlg.remove(), 300); });
    dlg.open = true;
  }

  ready(() => {
    const drawer = document.getElementById("nav-drawer");
    const toggle = document.getElementById("nav-toggle");
    if (toggle && drawer) toggle.addEventListener("click", () => { drawer.open = !drawer.open; });

    const themeBtn = document.getElementById("theme-toggle");
    if (themeBtn) themeBtn.addEventListener("click", () => {
      const root = document.documentElement;
      const cur = root.classList.contains("mdui-theme-dark") ? "dark"
        : root.classList.contains("mdui-theme-light") ? "light" : "auto";
      const next = cur === "dark" ? "light" : cur === "light" ? "auto" : "dark";
      const zh = { dark: "深色", light: "淺色", auto: "自動" };
      root.classList.remove("mdui-theme-auto", "mdui-theme-light", "mdui-theme-dark");
      root.classList.add("mdui-theme-" + next);
      window.toast("主題：" + zh[next]);
    });

    // 全域委派：複製 / 預覽（含動態加入的結果列）
    document.addEventListener("click", (ev) => {
      const cp = ev.target && ev.target.closest ? ev.target.closest("[data-copy]") : null;
      if (cp) { copyText(cp.getAttribute("data-copy")); return; }
      const pv = ev.target && ev.target.closest ? ev.target.closest("[data-preview]") : null;
      if (pv) preview(pv.getAttribute("data-preview"), pv.getAttribute("data-name") || "");
    });

    // 上傳 / 建資料夾頁籤
    document.querySelectorAll("[data-tabs]").forEach((tabs) => {
      const root = tabs.parentElement;
      const show = (v) => {
        try { tabs.value = v; } catch {}
        root.querySelectorAll("[data-tabpanel]").forEach((p) => { p.hidden = p.getAttribute("data-tabpanel") !== v; });
      };
      tabs.querySelectorAll("mdui-tab").forEach((t) => t.addEventListener("click", () => show(t.getAttribute("value"))));
    });

    // 分段上傳（公開 + 私人共用，data-merge 指向各自合併端點）
    document.querySelectorAll("form[data-chunked]").forEach((form) => {
      form.addEventListener("submit", (ev) => { ev.preventDefault(); chunkedUpload(form); });
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
        const input = form.querySelector('[name="name"]');
        const name = input && input.value.trim();
        if (!name) { window.toast("請輸入資料夾名稱"); return; }
        try {
          const res = await fetch("/api/folders", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name }),
          });
          if (!res.ok) throw new Error("HTTP " + res.status);
          window.toast("資料夾已建立");
          window.location.reload();
        } catch { window.toast("建立失敗"); }
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
          window.toast("分享連結已建立");
          window.location.reload();
        } catch { window.toast("建立失敗"); }
      });
    });
    document.querySelectorAll("[data-unshare]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!window.confirm("確定取消這個分享連結嗎？")) return;
        try {
          const res = await fetch("/api/share/revoke", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: btn.getAttribute("data-unshare") }),
          });
          if (!res.ok) throw new Error("HTTP " + res.status);
          window.toast("已取消分享");
          window.location.reload();
        } catch { window.toast("取消失敗"); }
      });
    });

    // 刪除私人資料夾（含其中的檔案）
    document.querySelectorAll("[data-delete-dir]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const name = btn.getAttribute("data-name") || "";
        const count = btn.getAttribute("data-count") || "0";
        if (window.confirm(`確定刪除資料夾「${name}」（含 ${count} 個檔案）嗎？無法復原。`)) {
          window.location.href = btn.getAttribute("data-delete-dir");
        }
      });
    });

    // 刪除確認
    document.querySelectorAll("[data-delete]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const name = btn.getAttribute("data-name") || "";
        if (window.confirm(`確定要刪除「${name}」嗎？此動作無法復原。`)) {
          window.location.href = btn.getAttribute("data-delete");
        }
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
      const card = bar.closest(".card-pad");
      const list = card ? card.querySelector("mdui-list") : null;
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
          const nameInput = host ? host.querySelector('[name="mkdir-name"]') : null;
          const body = nameInput && nameInput.value.trim() ? { name: nameInput.value.trim() } : {};
          const res = await fetch("/api/public/folder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          const data = await res.json();
          const out = host ? host.querySelector("[data-upload-result]") : null;
          if (out) {
            const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
            const title = data.folder_name ? esc(data.folder_name) : "資料夾已建立";
            out.innerHTML = `<mdui-card variant="filled" class="card-pad result-box">
              <div><strong>${title}</strong></div>
              <div class="rlink"><code>${esc(data.folder_url)}</code><span class="rlink-btns">` +
              `<a href="${esc(data.folder_url)}"><mdui-button variant="text">開啟</mdui-button></a>` +
              `<mdui-button variant="text" data-copy="${esc(data.folder_url)}">複製</mdui-button></span></div></mdui-card>`;
            window.toast("資料夾已建立");
          } else {
            window.location.href = data.folder_url;
          }
        } catch { window.toast("無法建立資料夾"); }
        finally { btn.loading = false; }
      });
    });
  });
})();
