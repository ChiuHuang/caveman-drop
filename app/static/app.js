// Shared browser helpers: drawer, theme toggle, copy buttons, uploads.
(function () {
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
      root.classList.remove("mdui-theme-auto", "mdui-theme-light", "mdui-theme-dark");
      root.classList.add("mdui-theme-" + next);
      window.toast("Theme: " + next);
    });

    document.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(btn.getAttribute("data-copy"));
          window.toast("Link copied");
        } catch { window.toast("Copy failed"); }
      });
    });

    // AJAX upload forms: POST multipart, render returned links without reload.
    document.querySelectorAll("form[data-ajax-upload]").forEach((form) => {
      form.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const out = form.parentElement.querySelector("[data-upload-result]");
        const btn = form.querySelector("[type=submit]");
        const fd = new FormData(form);
        if (btn) btn.loading = true;
        try {
          const res = await fetch(form.action, { method: "POST", body: fd });
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
          const links = [data.download_url || data.url, data.folder_url || data.share_url]
            .filter(Boolean).map((u) => `<div><a href="${u}"><code>${u}</code></a>
              <mdui-button variant="text" data-copy="${u}">Copy</mdui-button></div>`).join("");
          if (out) {
            out.innerHTML = `<mdui-card variant="filled" class="card-pad result-box">
              <div><strong>Uploaded:</strong> ${data.filename} (${data.size_bytes} bytes)</div>${links}</mdui-card>`;
            out.querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", async () => {
              try { await navigator.clipboard.writeText(b.getAttribute("data-copy")); window.toast("Link copied"); }
              catch { window.toast("Copy failed"); }
            }));
          }
          window.toast("Upload complete");
        } catch (err) { window.toast("Upload failed: " + err.message); }
        finally { if (btn) btn.loading = false; }
      });
    });

    // Create-folder buttons.
    document.querySelectorAll("[data-create-folder]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const res = await fetch("/api/public/folder", { method: "POST" });
          const data = await res.json();
          window.location.href = data.folder_url;
        } catch { window.toast("Could not create folder"); }
      });
    });
  });
})();
