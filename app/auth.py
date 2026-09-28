"""Authentication helpers.

Two ways in:

* a session cookie set by ``POST /login`` (the normal browser path), or
* ``?auth=<PASSWORD>`` on the request — for clients that go through a CORS-style
  proxy (``https://proxy.example/https://this.host/...``), which forwards the
  request but never hands our ``Set-Cookie`` back to the browser, so a cookie
  session cannot work that way.

``?auth=`` is only honoured over HTTPS, is never echoed back into any response
or redirect, and repeated failures from one IP are throttled.
"""

from __future__ import annotations

import hmac
import time

from fastapi import HTTPException, Request

from .config import settings
from .negotiation import wants_html
from .storage import client_ip
from .urls import is_https

AUTH_MAX_FAILS = 10
AUTH_FAIL_WINDOW = 600.0

_fails: dict[str, list[float]] = {}


def _too_many(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _fails.get(ip, []) if now - t < AUTH_FAIL_WINDOW]
    _fails[ip] = hits
    return len(hits) >= AUTH_MAX_FAILS


def _note_failure(ip: str) -> None:
    now = time.time()
    if len(_fails) > 4096:
        _fails.clear()
    _fails.setdefault(ip, []).append(now)


def query_auth_ok(request: Request, raising: bool = True) -> bool:
    """True when ``?auth=<PASSWORD>`` matches. HTTPS only.

    A wrong value counts against the IP; once the budget is spent the guard
    raises 429 (with ``raising=False`` it just reports False, for probes that
    should keep returning a plain 401).
    """
    got = (request.query_params.get("auth") or "").strip()
    if not got or not is_https(request):
        return False
    ip = client_ip(request)
    if _too_many(ip):
        if raising:
            raise HTTPException(429, "Too many failed ?auth= attempts, try again later")
        return False
    if hmac.compare_digest(got, settings.password):
        return True
    _note_failure(ip)
    return False


def authed(request: Request) -> bool:
    """Signed in by session cookie or by a valid ``?auth=`` parameter."""
    if request.session.get("auth"):
        return True
    return query_auth_ok(request, raising=wants_html(request))
