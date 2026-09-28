"""Language selection and UI strings.

Chinese (Traditional, zh-TW) is served to clients on the Taiwan ISP ranges
listed in ``TW_NETWORKS``; every other address gets English. ``?lang=en`` /
``?lang=zh-TW`` overrides the detection, which is handy for testing and for
anyone who wants the other language.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from fastapi import Request

from .storage import client_ip

ZH = "zh-TW"
EN = "en"

# Taiwan ISP / Taipei-region blocks. Everything else is served English.
# Note: 120.120.0.0 - 120.123.255.255 is not a single CIDR (the second octet
# varies), so it is listed as four /16s.
TW_NETWORKS = [
    ipaddress.ip_network("1.32.208.0/21"),    # 1.32.208.0 - 1.32.215.255
    ipaddress.ip_network("36.224.0.0/12"),     # 36.224.0.0 - 36.239.255.255
    ipaddress.ip_network("120.120.0.0/16"),    # 120.120.0.0 - 120.123.255.255
    ipaddress.ip_network("120.121.0.0/16"),
    ipaddress.ip_network("120.122.0.0/16"),
    ipaddress.ip_network("120.123.0.0/16"),
    ipaddress.ip_network("220.135.0.0/16"),   # 220.135.0.0 - 220.135.255.255
]

_cache: dict[str, str] = {}


def is_taiwan(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return False
    return any(addr in net for net in TW_NETWORKS)


def lang_for(request: Request) -> str:
    """zh-TW for Taiwan client IPs, English for everyone else."""
    want = (request.query_params.get("lang") or "").strip().lower()
    if want in ("en", "english"):
        return EN
    if want in ("zh", "zh-tw", "zh_tw", "zh-hant", "chinese"):
        return ZH
    ip = client_ip(request)
    hit = _cache.get(ip)
    if hit is None:
        hit = ZH if is_taiwan(ip) else EN
        if len(_cache) > 4096:
            _cache.clear()
        _cache[ip] = hit
    return hit


def other(lang: str) -> str:
    """The other language — used for the manual switch link."""
    return EN if lang == ZH else ZH


# Every user-facing string, keyed. `{}`-style placeholders are filled in order.
STRINGS: dict[str, dict[str, str]] = {
    "lang_zh": {ZH: "繁體中文", EN: "English"},
    "lang_switch_tip": {ZH: "切換語言", EN: "Switch language"},
    "site_name": {ZH: "CaveMan Drop", EN: "CaveMan Drop"},
    "nav_home": {ZH: "首頁", EN: "Home"},
    "nav_upload": {ZH: "上傳", EN: "Upload"},
    "nav_api": {ZH: "API", EN: "API"},
    "nav_docs": {ZH: "文件", EN: "Docs"},
    "nav_login": {ZH: "登入", EN: "Sign in"},
    "nav_logout": {ZH: "登出", EN: "Sign out"},
    "tagline": {
        ZH: "免帳號的匿名檔案分享。傳檔後立刻拿到永久連結。",
        EN: "Anonymous file sharing, no account. Permanent link the moment it lands.",
    },
    "home_h1": {ZH: "CaveMan Drop", EN: "CaveMan Drop"},
    "home_docs": {ZH: "使用文件", EN: "Read the docs"},
    "home_login": {ZH: "登入", EN: "Sign in"},
    "public_upload_h": {ZH: "公開上傳", EN: "Public upload"},
    "upload_h1": {ZH: "公開上傳", EN: "Public upload"},
    "upload_files_h": {ZH: "上傳檔案", EN: "Upload files"},
    "tab_upload": {ZH: "上傳檔案", EN: "Upload"},
    "tab_mkdir": {ZH: "建立資料夾", EN: "Create folder"},
    "folder_field": {ZH: "資料夾（選填）", EN: "Folder (optional)"},
    "desc_field": {ZH: "說明（選填）", EN: "Description (optional)"},
    "file_pick": {ZH: "選擇檔案", EN: "Choose file"},
    "btn_upload": {ZH: "上傳", EN: "Upload"},
    "btn_add_folder": {ZH: "加進資料夾", EN: "Add to folder"},
    "btn_start": {ZH: "開始上傳", EN: "Start upload"},
    "folder_name_field": {ZH: "資料夾名稱", EN: "Folder name"},
    "btn_create_folder": {ZH: "建立", EN: "Create"},
    "curl_h": {ZH: "curl 用法", EN: "curl"},
    "limits": {
        ZH: "單檔上限 {gb} GB・資料夾每 {mins} 分鐘合計上限 {fgb} GB・超量自動降速。",
        EN: "Up to {gb} GB per file · {fgb} GB per folder per {mins} min · throttled past that.",
    },
    "drop_hint": {ZH: "放開手上傳", EN: "Drop to upload"},
    "to_folder": {ZH: "已上傳到 {name}", EN: "Uploaded to {name}"},
    # thread panel
    "tp_pause": {ZH: "暫停", EN: "Pause"},
    "tp_resume": {ZH: "繼續", EN: "Resume"},
    "tp_paused": {ZH: "已暫停", EN: "Paused"},
    "tp_idle": {ZH: "待命中", EN: "Idle"},
    "tp_live": {ZH: "上傳中 #{n}", EN: "Uploading #{n}"},
    "tp_done": {ZH: "完成 #{n}", EN: "Done #{n}"},
    "tp_failed": {ZH: "失敗", EN: "Failed"},
    "tp_paused_toast": {ZH: "已暫停", EN: "Paused"},
    "tp_resumed_toast": {ZH: "繼續上傳", EN: "Resumed"},
    "tp_chunks": {ZH: "分段：{chunks}", EN: "Segments: {chunks}"},
    "tp_threads": {ZH: " · {n} 線程", EN: " · {n} threads"},
    "speed_pieces": {
        ZH: "{rate}/s（{mbps} Mbps）· {sent} / {total}{left}",
        EN: "{rate}/s ({mbps} Mbps) · {sent} / {total}{left}",
    },
    "speed_left": {ZH: " · 剩 {t}", EN: " · {t} left"},
    "speed_done": {ZH: "完成 · 平均 {rate}/s", EN: "Done · {rate}/s average"},
    "speed_link": {ZH: "連線 {mbps} Mbps · {n} 線程", EN: "{mbps} Mbps · {n} threads"},
    "throttled": {
        ZH: "分享頻寬限速中（約 {mbps} Mbps），上傳繼續",
        EN: "Bandwidth throttled to about {mbps} Mbps, still uploading",
    },
    "speed_unit_sec": {ZH: "{n} 秒", EN: "{n}s"},
    "speed_unit_min": {ZH: "{m} 分 {s} 秒", EN: "{m}m {s}s"},
    "speed_unit_hour": {ZH: "{h} 小時 {m} 分", EN: "{h}h {m}m"},
    # results
    "result_done": {ZH: "上傳完成", EN: "Upload complete"},
    "result_folder_made": {ZH: "資料夾已建立", EN: "Folder created"},
    "result_stats": {
        ZH: "{size} · {secs} 秒 · 平均 {rate}/s{dup}",
        EN: "{size} · {secs}s · {rate}/s average{dup}",
    },
    "result_dup": {ZH: " · 內容已存在，未重複儲存", EN: " · already stored, not duplicated"},
    "row_link": {ZH: "連結", EN: "Link"},
    "row_file": {ZH: "檔案", EN: "File"},
    "row_direct": {ZH: "直連", EN: "Direct"},
    "row_folder": {ZH: "資料夾", EN: "Folder"},
    "btn_copy": {ZH: "複製", EN: "Copy"},
    "btn_open": {ZH: "開啟", EN: "Open"},
    "btn_preview": {ZH: "預覽", EN: "Preview"},
    "btn_download": {ZH: "下載", EN: "Download"},
    "btn_delete": {ZH: "刪除", EN: "Delete"},
    "btn_direct_link": {ZH: "直接連結", EN: "Direct link"},
    "btn_copy_link": {ZH: "複製連結", EN: "Copy link"},
    "btn_cancel": {ZH: "取消", EN: "Cancel"},
    "toast_copied": {ZH: "連結已複製", EN: "Link copied"},
    "toast_copy_fail": {ZH: "複製失敗", EN: "Copy failed"},
    # lists
    "empty_folder": {ZH: "這個資料夾還沒有檔案。", EN: "This folder is empty."},
    "empty_files": {ZH: "還沒有檔案。", EN: "No files yet."},
    "private_h1": {ZH: "私人模式", EN: "Private mode"},
    "private_logged_in": {ZH: "已登入", EN: "Signed in"},
    "tab_public": {ZH: "公開（{n}）", EN: "Public ({n})"},
    # private drive
    "drive_title": {ZH: "我的雲端", EN: "My drive"},
    "drive_new_folder": {ZH: "新增資料夾", EN: "New folder"},
    "drive_items": {ZH: "{n} 個項目", EN: "{n} items"},
    "drive_files_h": {ZH: "{name} · 檔案（{n}）", EN: "{name} · Files ({n})"},
    "tab_public_short": {ZH: "公開", EN: "Public"},
    "btn_rename": {ZH: "改名", EN: "Rename"},
    "dialog_rename_h": {ZH: "改名", EN: "Rename"},
    "dialog_name": {ZH: "名稱", EN: "Name"},
    "btn_save": {ZH: "儲存", EN: "Save"},
    "toast_rename_ok": {ZH: "已改名", EN: "Renamed"},
    "toast_rename_fail": {ZH: "改名失敗", EN: "Rename failed"},
    "uncategorised": {ZH: "未分類", EN: "Uncategorised"},
    "share_view_link": {ZH: "檢視連結", EN: "View link"},
    "share_upload_link": {ZH: "上傳連結", EN: "Upload link"},
    "share_view_only": {ZH: "僅檢視", EN: "View only"},
    "share_can_upload": {ZH: "可上傳", EN: "Can upload"},
    "moved": {ZH: "已移到 {name}", EN: "Moved to {name}"},
    "moved_out": {ZH: "已移出資料夾", EN: "Removed from folder"},
    "no_cross": {ZH: "不能跨公開／私人移動", EN: "Cannot move across public and private"},
    "switch_tab_first": {ZH: "先切到可以上傳的分頁", EN: "Switch to an upload tab first"},
    # login
    "login_h": {ZH: "登入私人模式", EN: "Sign in to private mode"},
    "login_p": {ZH: "登入後只會看到私人空間。公開上傳不需要登入。", EN: "Once signed in you see only the private space. Public upload needs no account."},
    "login_pw": {ZH: "密碼", EN: "Password"},
    "login_btn": {ZH: "登入", EN: "Sign in"},
    "login_err": {ZH: "密碼錯誤，請再試一次。", EN: "Wrong password, try again."},
    # folder / share pages
    "folder_public": {ZH: "公開資料夾 · {n} 個檔案", EN: "Public folder · {n} files"},
    "copy_share": {ZH: "複製分享連結", EN: "Copy share link"},
    "add_here_h": {ZH: "加入檔案到此資料夾", EN: "Add files to this folder"},
    "private_mode_note": {ZH: "目前為私人模式。如需上傳公開檔案，請先登出。", EN: "You are in private mode. Sign out to upload public files."},
    "signout_first": {ZH: "登出以上傳公開檔案", EN: "Sign out to upload"},
    "share_folder_h": {ZH: "上傳到此資料夾", EN: "Upload to this folder"},
    "share_meta": {ZH: "分享資料夾 · {n} 個檔案 · {mode}", EN: "Shared folder · {n} files · {mode}"},
    "unnamed_folder": {ZH: "未命名資料夾", EN: "Untitled folder"},
    "not_found": {ZH: "找不到", EN: "Not found"},
    "not_found_folder": {ZH: "找不到這個資料夾。", EN: "That folder does not exist."},
    "not_found_any": {ZH: "這個網址沒有東西。", EN: "Nothing here."},
    "share_invalid": {ZH: "連結無效或已被取消。", EN: "This link is invalid or was revoked."},
    "share_gone": {ZH: "資料夾已刪除。", EN: "That folder was deleted."},
    # dialogs
    "confirm_del_dir": {
        ZH: "確定刪除資料夾「{name}」（含 {n} 個檔案）嗎？無法復原。",
        EN: "Delete folder “{name}” and its {n} files? This cannot be undone.",
    },
    "confirm_del_pubdir": {
        ZH: "確定刪除公開資料夾「{name}」（含 {n} 個檔案）嗎？",
        EN: "Delete public folder “{name}” and its {n} files?",
    },
    "confirm_del_file": {
        ZH: "確定要刪除「{name}」嗎？此動作無法復原。",
        EN: "Delete “{name}”? This cannot be undone.",
    },
    # toasts
    "toast_need_file": {ZH: "請先選擇檔案", EN: "Pick a file first"},
    "toast_fail": {ZH: "上傳失敗：{err}", EN: "Upload failed: {err}"},
    "toast_merge_fail": {ZH: "合併失敗：{err}", EN: "Merge failed: {err}"},
    "toast_merging": {ZH: "合併中…", EN: "Merging…"},
    "toast_folder_made": {ZH: "資料夾已建立", EN: "Folder created"},
    "toast_folder_fail": {ZH: "無法建立資料夾", EN: "Could not create the folder"},
    "toast_need_name": {ZH: "請輸入資料夾名稱", EN: "Give the folder a name"},
    "toast_mkdir_ok": {ZH: "資料夾已建立", EN: "Folder created"},
    "toast_mkdir_fail": {ZH: "建立失敗", EN: "Could not create"},
    "toast_share_ok": {ZH: "分享連結已建立", EN: "Share link created"},
    "toast_unshare_ok": {ZH: "已取消分享", EN: "Share revoked"},
    "toast_unshare_fail": {ZH: "取消失敗", EN: "Could not revoke"},
    "toast_move_fail": {ZH: "移動失敗", EN: "Move failed"},
    "toast_deleted": {ZH: "已刪除", EN: "Deleted"},
    "toast_delete_fail": {ZH: "刪除失敗", EN: "Delete failed"},
    "toast_dl_done": {ZH: "下載完成", EN: "Download complete"},
    "toast_dl_fail": {ZH: "下載失敗，改用直接下載", EN: "Download failed, using a direct link"},
    "toast_theme": {ZH: "主題：{v}", EN: "Theme: {v}"},
    "theme_dark": {ZH: "深色", EN: "Dark"},
    "theme_light": {ZH: "淺色", EN: "Light"},
    "theme_auto": {ZH: "自動", EN: "Auto"},
    "sort_by": {ZH: "排序：", EN: "Sort: "},
    "sort_time": {ZH: "時間", EN: "Time"},
    "sort_size": {ZH: "大小", EN: "Size"},
    "sort_name": {ZH: "名稱", EN: "Name"},
    "drag_preview": {ZH: "放到「{name}」", EN: "Drop into “{name}”"},
    "drag_folder": {ZH: "放到這個資料夾", EN: "Drop into this folder"},
    "upload_multi": {ZH: "上傳 {i}/{n}：{name}", EN: "Uploading {i}/{n}: {name}"},
    "api_index_h": {ZH: "API 索引", EN: "API index"},
    "api_index_p": {
        ZH: "以下每個端點：程式與 AI 拿到 JSON（加 ?format=json 可強制），瀏覽器則看到 MDUI 控制台。",
        EN: "Each endpoint below: scripts and AI get JSON (force it with ?format=json), browsers get the MDUI console.",
    },
    "ai_docs": {ZH: "給 AI 的 llms.txt", EN: "llms.txt for AI"},
    "full_ref": {ZH: "完整參考", EN: "Full reference"},
    "preview_title": {ZH: "預覽 — {name}", EN: "Preview — {name}"},
    "btn_close": {ZH: "關閉", EN: "Close"},
    "api_console_h": {ZH: "資料夾 API 控制台", EN: "Folder API console"},
    "api_console_open": {ZH: "開啟資料夾介面", EN: "Open folder UI"},
    "copy_api_url": {ZH: "複製 API 網址", EN: "Copy API URL"},
    "open_folder": {ZH: "開啟資料夾", EN: "Open folder"},
    "files_h": {ZH: "檔案（{n}）", EN: "Files ({n})"},
    "api_h": {ZH: "API", EN: "API"},
    "files_api": {ZH: "檔案 API", EN: "Files API"},
    "private_cloud_h": {ZH: "私人雲端", EN: "Private cloud"},
    "back_home": {ZH: "回私人模式首頁", EN: "Back to private mode"},
    "docs_kicker": {ZH: "文件", EN: "Docs"},
}


def t(lang: str, key: str, **kw: Any) -> str:
    """Look up a string for `lang`, falling back to English then the key."""
    row = STRINGS.get(key) or {}
    text = row.get(lang) or row.get(EN) or key
    if kw:
        try:
            return text.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text
    return text
