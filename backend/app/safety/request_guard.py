"""One guard in front of every request.

1. **Shop hosts serve shop pages only.** `<name>.<APP_DOMAIN>` never answers /api, /internal,
   /assets, /build or /r: the app's API simply doesn't exist there. (The session cookie is
   host-only and isn't sent to shop hosts anyway; this is a second wall.)
2. **Origin check.** A state-changing /api request must come from the app's own origin
   (`Origin`, or else `Referer`). A request with neither is allowed only when it carries no
   cookie at all (command-line tools using the admin token).
3. **CSRF token.** If the request carries the session (or guest) cookie, it must also carry
   `X-CSRF-Token`, a value derived from that cookie which only our own pages can learn.
"""

import hmac
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.config import get_settings
from app.safety.access import csrf_for
from app.sites.hosts import normalize_host, subdomain_label

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
APP_ONLY = ("/api/", "/internal/", "/assets/", "/build", "/r/")
STALE = "This page is out of date. Please refresh it and try again."


def origin_of(value: str | None) -> str | None:
    if not value:
        return None
    u = urlsplit(value)
    return f"{u.scheme}://{u.netloc}".lower() if u.scheme and u.netloc else None


def refuse(message: str = STALE) -> JSONResponse:
    return JSONResponse({"detail": message}, status_code=403)


async def request_guard(request: Request, call_next):
    settings = request.app.dependency_overrides.get(get_settings, get_settings)()
    path = request.url.path
    on_shop_host = subdomain_label(normalize_host(request.headers.get("host", "")), settings) is not None
    if on_shop_host and (path.startswith(APP_ONLY) or path == "/api"):
        return PlainTextResponse("Not found", status_code=404)
    if request.method in UNSAFE and path.startswith("/api/"):
        origin = origin_of(request.headers.get("origin")) or origin_of(request.headers.get("referer"))
        cookie = request.cookies.get(settings.session_cookie) or request.cookies.get(settings.guest_cookie)
        if origin is None:
            if cookie:
                return refuse()
        elif origin != settings.origin:
            return refuse()
        if cookie:
            sent = request.headers.get("x-csrf-token", "")
            valid = [csrf_for(v) for v in (request.cookies.get(settings.session_cookie),
                                           request.cookies.get(settings.guest_cookie)) if v]
            if not sent or not any(hmac.compare_digest(sent, v) for v in valid):
                return refuse()
    return await call_next(request)
