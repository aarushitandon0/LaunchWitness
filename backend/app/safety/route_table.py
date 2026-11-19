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
    ("GET", "/api/themes"): PUBLIC,  # S14: the six shop themes + accents (picker data; nothing private)
    ("POST", "/api/contact"): PUBLIC,
    ("POST", "/api/check-address"): PUBLIC,  # read-only checks of any address; SSRF-guarded, rate-limited
    ("POST", "/api/proof/confirm"): PUBLIC,  # "Yes, I got it": the single-use token is the permission
    ("GET", "/r/{token}"): PUBLIC,  # shared read-only report: the unguessable, revocable token is the permission
    ("GET", "/r/{token}/verify"): PUBLIC,  # recomputes the proof chain: intact/rows/head only; same token, rate-limited
    # --- public shop pages (served on shop hosts only) ---
    ("POST", "/order"): PUBLIC,
    ("POST", "/report-shop"): PUBLIC,
    # --- demo shops (S10.5): sample profiles, no database row, the form places no order ---
    ("GET", "/shop-assets/fonts/{file}"): PUBLIC,  # S14: the shop themes' self-hosted woff2 files (on every host)
    ("GET", "/photos/{file}"): PUBLIC,  # S12: on a shop host only its own photos; on the app host by random name
    ("GET", "/demo/{name}"): PUBLIC,
    ("GET", "/demo/{name}/privacy"): PUBLIC,
    ("POST", "/demo/{name}/order"): PUBLIC,
    # --- sign-in ---
    ("POST", "/api/auth/request-link"): PUBLIC,
    ("POST", "/api/auth/confirm"): PUBLIC,
    ("GET", "/api/auth/me"): PUBLIC,
    ("POST", "/api/auth/logout"): PUBLIC,  # ends the caller's own session, if any
    ("POST", "/api/auth/logout-all"): AUTH,
    ("POST", "/api/account/delete-request"): AUTH,
    ("POST", "/api/account/delete"): AUTH,
    # --- watched addresses (S10.5b): the caller's own only (filtered in the query; others' answer 404) ---
    ("GET", "/api/watches"): AUTH,
    ("POST", "/api/watches"): AUTH,  # max 3 per account, adds rate-limited, read-only checks via SafeWeb
    ("DELETE", "/api/watches/{watch_id}"): AUTH,
    # --- shops: creating and listing are open to guests (practice), and only ever touch the caller's own ---
    ("POST", "/api/businesses"): PUBLIC,
    ("GET", "/api/businesses"): PUBLIC,
    # --- everything that belongs to one business ---
    ("GET", "/api/businesses/{business_id}"): OWNER,
    ("PUT", "/api/businesses/{business_id}"): OWNER,
    ("POST", "/api/businesses/{business_id}/reread"): OWNER,  # S17 back to Describe: one Claude reading, daily cap
    ("DELETE", "/api/businesses/{business_id}"): OWNER,
    ("GET", "/api/businesses/{business_id}/preview"): OWNER,
    ("GET", "/api/businesses/{business_id}/orders"): OWNER,
    ("POST", "/api/businesses/{business_id}/orders/{order_id}/status"): OWNER,  # S10.5: New → Confirmed → Paid → Done
    ("GET", "/api/businesses/{business_id}/export"): OWNER,
    ("POST", "/api/businesses/{business_id}/describe-problem"): OWNER,  # S12: symptom → Doctor (data), 5/day per user
    ("PUT", "/api/businesses/{business_id}/theme"): OWNER,  # S14: the owner's look; fixed keys only, audited
    ("GET", "/api/businesses/{business_id}/photos"): OWNER,  # S12 product photos
    ("POST", "/api/businesses/{business_id}/photos"): OWNER,  # content-checked, re-encoded, stripped, 60/day per shop
    ("DELETE", "/api/businesses/{business_id}/photos/{photo_id}"): OWNER,
    ("GET", "/api/businesses/{business_id}/golive"): OWNER,  # S10.5 go-live checklist
    ("POST", "/api/businesses/{business_id}/confirm"): OWNER,  # owner-confirmed steps; the team gets 404 too
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
    ("GET", "/api/admin/outbox"): ADMIN,
    ("PUT", "/api/admin/practice-mail"): ADMIN,
    ("POST", "/api/admin/users/{user_id}/approve"): ADMIN,
    ("POST", "/api/admin/users/{user_id}/reject"): ADMIN,
    ("POST", "/api/admin/users/{user_id}/suspend"): ADMIN,
    ("GET", "/api/admin/businesses"): ADMIN,
    ("POST", "/api/admin/businesses/{business_id}/pause"): ADMIN,
    ("POST", "/api/admin/businesses/{business_id}/unpause"): ADMIN,
    ("POST", "/api/admin/businesses/{business_id}/clear-review"): ADMIN,
    ("POST", "/api/admin/businesses/{business_id}/publish-edit"): ADMIN,
    ("POST", "/api/admin/businesses/{business_id}/discard-edit"): ADMIN,
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
