// CaveMan Drop 瀏覽器互動：側欄、主題、複製、公開上傳、
// 16 線程分段上傳、16 線程下載、預覽、刪除確認。
(function () {
  const THREADS = 16;
  const CHUNK = 4 * 1024 * 1024; // 4 MB per upload chunk

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

  // ---- 16 線程分段上傳 ----
  async function chunkedUpload(form) {
    const input = form.querySelector('input[type="file"]');
    const file = input && input.files[0];
    if (!file) { window.toast("請先選擇檔案"); return; }
    const btn = form.querySelector("[type=submit]");
    const bar = form.querySelector("[data-progress]");
    const txt = form.querySelector("[data-progress-text]");
    const total = Math.max(1, Math.ceil(file.size / CHUNK));
    const uploadId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()));
    let next = 0, done = 0, failed = null;

    if (btn) btn.loading = true;
    if (bar) bar.style.display = "";
    const show = () => { if (txt) txt.textContent = `上傳中… ${done}/${total} 塊`; };
    show();

    async function worker() {
      while (next < total && !failed) {
        const i = next++;
        const fd = new FormData();
        fd.append("file_chunk", file.slice(i * CHUNK, (i + 1) * CHUNK), "chunk");
        fd.append("upload_id", uploadId);
        fd.append("index", String(i));
        fd.append("filename", file.name);
        try {
          const res = await fetch(form.action, { method: "POST", body: fd });
          if (!res.ok) throw new Error("HTTP " + res.status);
        } catch (err) { failed = err; return; }
        done++; show();
      }
    }

    await Promise.all(Array.from({ length: Math.min(THREADS, total) }, worker));
    if (failed) {
      window.toast("上傳失敗：" + failed.message);
      if (btn) btn.loading = false;
      return;
    }
    try {
      const res = await fetch("/api/merge_chunks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upload_id: uploadId, filename: file.name, total_chunks: total }),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      window.toast("上傳完成");
      window.location.reload();
    } catch (err) {
      window.toast("合併失敗：" + err.message);
      if (btn) btn.loading = false;
    }
  }

  // ---- 16 線程下載：Range 分段並行抓取後合併 ----
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
      window.toast(`16 線程下載中… ${name}`);
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
      window.toast("多線程下載失敗，改用直接下載");
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

    document.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", () => copyText(btn.getAttribute("data-copy")));
    });

    // 公開上傳（單次 POST，後端串流寫入）
    document.querySelectorAll("form[data-ajax-upload]").forEach((form) => {
      form.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const out = form.parentElement.querySelector("[data-upload-result]");
        const btn = form.querySelector("[type=submit]");
        if (btn) btn.loading = true;
        try {
          const res = await fetch(form.action, { method: "POST", body: new FormData(form) });
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
          const links = [data.download_url || data.url, data.folder_url || data.share_url]
            .filter(Boolean).map((u) => `<div><a href="${u}"><code>${u}</code></a>
              <mdui-button variant="text" data-copy="${u}">複製</mdui-button></div>`).join("");
          if (out) {
            out.innerHTML = `<mdui-card variant="filled" class="card-pad result-box">
              <div><strong>已上傳：</strong> ${data.filename} (${data.size_bytes} 位元組)</div>${links}</mdui-card>`;
            out.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => copyText(b.getAttribute("data-copy"))));
          }
          window.toast("上傳完成");
        } catch (err) { window.toast("上傳失敗：" + err.message); }
        finally { if (btn) btn.loading = false; }
      });
    });

    // 私人 16 線程分段上傳
    document.querySelectorAll("form[data-chunked]").forEach((form) => {
      form.addEventListener("submit", (ev) => { ev.preventDefault(); chunkedUpload(form); });
    });

    // 16 線程下載
    document.querySelectorAll("[data-mt-download]").forEach((btn) => {
      btn.addEventListener("click", () => mtDownload(btn));
    });

    // 預覽
    document.querySelectorAll("[data-preview]").forEach((btn) => {
      btn.addEventListener("click", () => preview(btn.getAttribute("data-preview"), btn.getAttribute("data-name") || ""));
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

    // 建立空資料夾
    document.querySelectorAll("[data-create-folder]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const res = await fetch("/api/public/folder", { method: "POST" });
          const data = await res.json();
          window.location.href = data.folder_url;
        } catch { window.toast("無法建立資料夾"); }
      });
    });
  });
})();
