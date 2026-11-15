"""Every route of the app, classified. A route that isn't listed here can't ship: a test walks
the real app and fails on any route missing from this table (and on any stale entry), and
checks that each route really uses the gate its class promises.

Classes
- public:   anyone. No sign-in needed. (Lists and creations are still limited to the caller's own things.)
- auth:     a signed-in user (`require_user`).
- owner:    the owner of the business in the URL (`require_business_access` / `require_plan_access`);
            someone else's id answers 404.
- admin:    the team (`require_admin`).
- internal: only reachable on the private network (Caddy answers 404 for /internal/* from outside).
"""

from collections.abc import Iterator

PUBLIC, AUTH, OWNER, ADMIN, INTERNAL = "public", "auth", "owner", "admin", "internal"

ROUTES: dict[tuple[str, str], str] = {
    # --- app shell and public pages ---
    ("GET", "/{path:path}"): PUBLIC,  # landing page, built frontend, /build; on a shop host: the shop's pages
    ("MOUNT", "/assets"): PUBLIC,
    ("GET", "/api/health"): PUBLIC,
    ("GET", "/api/samples"): PUBLIC,
    ("POST", "/api/contact"): PUBLIC,
    ("POST", "/api/check-address"): PUBLIC,  # read-only checks of any address; SSRF-guarded, rate-limited
    ("POST", "/api/proof/confirm"): PUBLIC,  # "Yes, I got it": the single-use token is the permission
    ("GET", "/r/{token}"): PUBLIC,  # shared read-only report: the unguessable, revocable token is the permission
    # --- public shop pages (served on shop hosts only) ---
    ("POST", "/order"): PUBLIC,
    ("POST", "/report-shop"): PUBLIC,
    # --- sign-in ---
    ("POST", "/api/auth/request-link"): PUBLIC,
    ("POST", "/api/auth/confirm"): PUBLIC,
    ("GET", "/api/auth/me"): PUBLIC,
    ("POST", "/api/auth/logout"): PUBLIC,  # ends the caller's own session, if any
    ("POST", "/api/auth/logout-all"): AUTH,
    ("POST", "/api/account/delete-request"): AUTH,
    ("POST", "/api/account/delete"): AUTH,
    # --- shops: creating and listing are open to guests (practice), and only ever touch the caller's own ---
    ("POST", "/api/businesses"): PUBLIC,
    ("GET", "/api/businesses"): PUBLIC,
    # --- everything that belongs to one business ---
    ("GET", "/api/businesses/{business_id}"): OWNER,
    ("PUT", "/api/businesses/{business_id}"): OWNER,
    ("DELETE", "/api/businesses/{business_id}"): OWNER,
    ("GET", "/api/businesses/{business_id}/preview"): OWNER,
    ("GET", "/api/businesses/{business_id}/orders"): OWNER,
    ("GET", "/api/businesses/{business_id}/export"): OWNER,
    ("GET", "/api/businesses/{business_id}/names"): OWNER,
    ("POST", "/api/businesses/{business_id}/plans"): OWNER,
    ("GET", "/api/businesses/{business_id}/plans"): OWNER,
    ("GET", "/api/businesses/{business_id}/report"): OWNER,
    ("POST", "/api/businesses/{business_id}/checks"): OWNER,
    ("GET", "/api/plans/{plan_id}"): OWNER,
    ("POST", "/api/plans/{plan_id}/approve"): OWNER,
    ("POST", "/api/plans/{plan_id}/resume"): OWNER,
    ("POST", "/api/plans/{plan_id}/practice-buy"): OWNER,
    ("GET", "/api/businesses/{business_id}/share"): OWNER,
    ("POST", "/api/businesses/{business_id}/share"): OWNER,
    ("DELETE", "/api/businesses/{business_id}/share"): OWNER,
    # --- team ---
    ("GET", "/api/admin/check"): ADMIN,
    ("GET", "/api/admin/users"): ADMIN,
    ("POST", "/api/admin/users/{user_id}/approve"): ADMIN,
    ("POST", "/api/admin/users/{user_id}/reject"): ADMIN,
    ("POST", "/api/admin/users/{user_id}/suspend"): ADMIN,
    ("GET", "/api/admin/businesses"): ADMIN,
    ("POST", "/api/admin/businesses/{business_id}/pause"): ADMIN,
    ("POST", "/api/admin/businesses/{business_id}/unpause"): ADMIN,
    ("POST", "/api/admin/businesses/{business_id}/clear-review"): ADMIN,
    ("PUT", "/api/admin/businesses/{business_id}/demo-fault"): ADMIN,
    ("DELETE", "/api/admin/practice-businesses/{business_id}"): ADMIN,
    ("GET", "/api/admin/reports"): ADMIN,
    ("POST", "/api/admin/reports/{report_id}/close"): ADMIN,
    ("GET", "/api/admin/zone-findings"): ADMIN,  # zone hygiene (S10): read
    ("POST", "/api/admin/zone-check"): ADMIN,  # reads the app zone, changes nothing
    ("POST", "/api/admin/zone-findings/{finding_id}/approve"): ADMIN,  # applies ONE proposed shop A-record fix
    ("POST", "/api/admin/zone-findings/{finding_id}/dismiss"): ADMIN,
    # --- private network only ---
    ("GET", "/internal/tls-ask"): INTERNAL,
}


def walk(routes) -> Iterator:
    """Every real route of the app, including those inside included routers."""
    for r in routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            yield from walk(inner.routes)
        else:
            yield r


def app_routes(app) -> list[tuple[str, str, object]]:
    """(METHOD, path, route) for every route; a mounted directory is METHOD "MOUNT"."""
    out = []
    for r in walk(app.routes):
        methods = [m for m in (getattr(r, "methods", None) or []) if m not in ("HEAD", "OPTIONS")]
        if not methods:
            out.append(("MOUNT", r.path, r))
        out.extend((m, r.path, r) for m in sorted(methods))
    return out


def gate_calls(route) -> set[str]:
    """Names of every dependency function the route uses (searched through sub-dependencies)."""
    seen: set[str] = set()

    def visit(dep) -> None:
        for d in getattr(dep, "dependencies", []):
            call = getattr(d, "call", None)
            if call is not None:
                seen.add(getattr(call, "__name__", ""))
            visit(d)

    if getattr(route, "dependant", None) is not None:
        visit(route.dependant)
    return seen
