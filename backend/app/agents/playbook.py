"""The ONLY repairs the Doctor may choose (SPEC §5, §9). Code applies them.

Every fix reuses the executor's guarded writes (backup exists, domain in DB,
one type+name at a time). No fix spends money. `fixes_for(check, mode)` limits which
fixes make sense for which failed check in which kind of launch.
"""

from collections.abc import Callable

from app import audit
from app.agents.executor import Ctx, StepFailed, restore_change, write_change
from app.agents.planner import DKIM_PENDING


def _changes(ctx: Ctx, pred) -> list[dict]:
    return [c for c in ctx.changes if pred(c)]


def _rewrite(ctx: Ctx, changes: list[dict]) -> str:
    if not changes:
        raise StepFailed("There's nothing in your plan to re-add for this.", "no matching planned change")
    for ch in changes:
        after = ch["after"]
        if ch["deferred"] or any(r.get("data") == DKIM_PENDING for r in after):
            _name, value = ctx.integ.mailbox.dkim(ctx.plan.zone)
            after = [{**r, "data": value} for r in after]
        write_change(ctx, ch, after)
    return f"Re-added {len(changes)} setting(s)."


def restore_backup(ctx: Ctx) -> str:
    """Undo: put every setting this launch touched back as it was before."""
    for ch in ctx.changes:
        restore_change(ctx, ch)
    return "Put your settings back the way they were before the launch."


def readd_mx(ctx: Ctx) -> str:
    return _rewrite(ctx, _changes(ctx, lambda c: c["type"] == "MX"))


def readd_email_auth(ctx: Ctx) -> str:
    return _rewrite(ctx, _changes(ctx, lambda c: c["type"] == "TXT"))


def repoint_site(ctx: Ctx) -> str:
    done = _rewrite(ctx, _changes(ctx, lambda c: c["type"] == "A"))
    heal = getattr(ctx.integ.shop_web, "staged_heal", None)  # only the staged "parked page" fault has this
    if heal is not None:
        heal()
    return done


def retry_certificate(ctx: Ctx) -> str:
    """Caddy issues the certificate on demand: a fresh HTTPS request triggers a new attempt.
    TODO(real): if Caddy keeps failing, its admin API can be asked to retry (see PROGRESS.md)."""
    ctx.integ.sleep(10)
    heal = getattr(ctx.integ.http, "staged_heal", None)  # only the staged demo fault has this (launch_check.py)
    if heal is not None:
        heal()
    ctx.integ.http.fetch(f"https://{ctx.plan.site_host}/")
    return "Asked for a new security certificate."


PLAYBOOK: dict[str, Callable[[Ctx], str]] = {
    "restore_backup": restore_backup,
    "readd_mx": readd_mx,
    "readd_email_auth": readd_email_auth,
    "retry_certificate": retry_certificate,
    "repoint_site": repoint_site,
}

# Which fixes make sense for which failed check, per launch mode.
# "sandbox" = a shop on <name>.<APP_DOMAIN>: the only setting that is the shop's own is its A
# record. Mail settings there belong to the app's domain and are never written by code, and a
# missing test order has no safe automatic fix, so those checks get no fix (and no Doctor call).
# "full" = a launch on the seller's own domain (practice only for now).
FIXES_FOR: dict[str, dict[str, set[str]]] = {
    "sandbox": {
        "site_points": {"repoint_site"},
        "https": {"retry_certificate", "repoint_site"},
    },
    "full": {
        "site_points": {"repoint_site", "restore_backup"},
        "https": {"retry_certificate", "repoint_site"},
        "email_mx": {"readd_mx"},
        "email_spf": {"readd_email_auth"},
        "email_dkim": {"readd_email_auth"},
        "email_dmarc": {"readd_email_auth"},
        "test_order": {"readd_mx", "readd_email_auth"},
    },
}


def fixes_for(check: str, mode: str) -> set[str]:
    return set(FIXES_FOR.get(mode, {}).get(check, set()))


def apply_fix(ctx: Ctx, fix_id: str) -> str:
    if fix_id not in PLAYBOOK:  # callers check first; this is the last line of defence
        raise ValueError(f"{fix_id} is not in the playbook")
    message = PLAYBOOK[fix_id](ctx)
    audit.record(ctx.session, actor="doctor", action=f"fix_{fix_id}", target=ctx.plan.site_host, result="ok",
                 business_id=ctx.business.id, detail=message)
    return message
