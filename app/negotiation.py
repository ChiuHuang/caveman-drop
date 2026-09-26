"""Browser vs. API-client content negotiation.

Browsers (browser UA + Accept: text/html) get HTML; scripts/agents get
JSON/text. `?format=html|json|text` forces one.
"""

from __future__ import annotations

from fastapi import Request

BROWSER_TOKENS = (
    "Mozilla",
    "AppleWebKit",
    "Gecko",
    "Chrome",
    "Safari",
    "Edg",
    "Firefox",
    "OPR",
    "SamsungBrowser",
)

NON_BROWSER_PREFIXES = (
    "curl/",
    "Wget/",
    "python-requests",
    "python-httpx",
    "httpx/",
    "Go-http-client",
    "PostmanRuntime",
)


def is_browser_ua(user_agent: str) -> bool:
    if not user_agent:
        return False
    lowered = user_agent.lower()
    for prefix in NON_BROWSER_PREFIXES:
        if lowered.startswith(prefix.lower()):
            return False
    return any(token.lower() in lowered for token in BROWSER_TOKENS)


def wants_html(request: Request) -> bool:
    fmt = request.query_params.get("format", "").lower()
    if fmt == "html":
        return True
    if fmt in ("json", "text", "txt"):
        return False
    accept = request.headers.get("accept", "")
    if "text/html" not in accept:
        return False
    return is_browser_ua(request.headers.get("user-agent", ""))
