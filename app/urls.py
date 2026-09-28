"""Absolute base URL used for every generated link.

Behind a TLS-terminating proxy (nginx, Cloudflare, the panel) the app only ever
sees plain HTTP, so ``request.base_url`` would hand out ``http://`` links even
when the visitor arrived over HTTPS. We therefore trust the standard forwarding
headers: a request that came in over HTTPS always gets HTTPS links back, and a
plain-HTTP request keeps ``http://``. ``PUBLIC_BASE_URL`` overrides everything
when even the forwarded headers are not enough.
"""

from __future__ import annotations

import re

from fastapi import Request

from .config import settings

# Hostname, optional port, or bracketed IPv6 — nothing that could break out of
# an attribute or a JSON string.
_HOST_RE = re.compile(r"^[A-Za-z0-9._~%!$&'()*+,;=\[\]:-]+$")
_PROTO_RE = re.compile(r"proto\s*=\s*\"?([A-Za-z]+)\"?")
_HOST_FWD_RE = re.compile(r"host\s*=\s*\"?([^\";,\s]+)\"?")


def _first(value: str | None) -> str:
    """First entry of a comma separated header list."""
    return (value or "").split(",")[0].strip()


def _scheme(request: Request) -> str:
    for name in ("forwarded", "x-forwarded-proto", "x-forwarded-ssl", "x-forwarded-protocol"):
        raw = request.headers.get(name) or ""
        match = _PROTO_RE.search(raw) if name == "forwarded" else None
        value = (match.group(1) if match else _first(raw)).lower()
        if value in ("http", "https"):
            return value
        if value in ("on", "ssl"):  # X-Forwarded-Ssl: on
            return "https"
    return request.url.scheme


def _host(request: Request) -> str:
    for name in ("x-forwarded-host", "forwarded"):
        raw = request.headers.get(name) or ""
        value = _first(raw) if name == "x-forwarded-host" else ""
        if not value:
            match = _HOST_FWD_RE.search(raw)
            value = match.group(1) if match else ""
        if value and _HOST_RE.fullmatch(value):
            return value
    return request.url.netloc


def base_url(request: Request) -> str:
    """`https://host` for this request, without a trailing slash."""
    if settings.public_base_url:
        return settings.public_base_url
    root = (request.scope.get("root_path") or "").rstrip("/")
    return f"{_scheme(request)}://{_host(request)}{root}"


def is_https(request: Request) -> bool:
    """True when the visitor reached us over HTTPS (directly or through a proxy)."""
    return base_url(request).startswith("https://")


def private_only(request: Request) -> bool:
    """True when this host serves the private drive and nothing else.

    `PRIVATE_ONLY_HOSTS` (default `pvf.chiuhuang.dev`) names the domains that are
    for signed-in use only: `/` is the login page when signed out, and the drive
    with no tabs or public UI when signed in. The public JSON API keeps working
    on those hosts, so scripts are unaffected.
    """
    hosts = settings.private_only_hosts
    if not hosts:
        return False
    netloc = _host(request).split("@")[-1].split(":")[0].lower()
    return netloc in hosts
