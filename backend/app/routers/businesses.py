"""Seller-facing API: read a business description, review/edit the profile, list orders."""

import json
import re
import secrets
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlmodel import Session, func, select

from app import accounts, audit, golive
from app.agents.claude_client import FALLBACK_NOTE, Claude, ClaudeBudgetExceeded, make_claude_client
from app.agents.reader import MAX_IMAGE_BYTES, Profile, ReaderError, read_business
from app.config import Settings, get_settings
from app.db import get_engine, get_session
from app.integrations import Integrations, for_business, get_integrations, get_practice_integrations
from app.models import AuditEvent, Business, Membership, Order, PaymentClaim, Plan, utcnow
from app.safety.access import (
    ActorDep,
    csrf_for,
    describes_today,
    owner_emails,
    require_business_access,
    sha,
    user_describes_today,
    visitor_id,
)
from app.sites import live_contact, motifs, themes
from app.sites.hosts import is_public, site_url, slug_problem
from app.sites.orders import STATUS_LABELS, STATUS_STEPS, can_move, customer_whatsapp_link, tel_link
from app.sites.render import render_site, upi_qr_svg, upi_uri
from app.tenancy import purge_business

router = APIRouter(prefix="/api", tags=["businesses"])
SELLERS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sellers"


def get_claude(settings: Annotated[Settings, Depends(get_settings)]) -> Claude:
    """FastAPI dependency. Tests override this."""
    return make_claude_client(settings, get_engine() if settings.claude_mode == "live" else None)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("'", "")).strip("-")
    s = s[:30].strip("-")
    return s if len(s) >= 3 else "shop"


def unique_subdomain(session: Session, base: str) -> str:
    if slug_problem(base) is not None:  # reserved or brand-like: start from a neutral name
        base = "shop"
    candidate, n = base, 2
    while slug_problem(candidate) is not None or session.exec(select(Business.id).where(Business.subdomain == candidate)).first():
        candidate, n = f"{base[:26]}-{n}", n + 1
    return candidate


def latest_plan(session: Session | None, b: Business) -> dict | None:
    """The shop's newest launch plan, so the app can resume the 5-step flow at the right step."""
    if session is None:
        return None
    p = session.exec(select(Plan).where(Plan.business_id == b.id).order_by(Plan.id.desc())).first()
    return {"id": p.id, "status": p.status, "practice": p.practice} if p else None


def business_out(b: Business, settings: Settings, session: Session | None = None) -> dict:
    owners = owner_emails(session, b.id) if session is not None else []
    return {
        "latest_plan": latest_plan(session, b),
        "name": b.name,
        "guest": bool(b.guest_hash),  # made without signing in: practice only, kept for 24 hours
        "paused": b.paused,
        "review": b.review,
        "review_reason": b.review_reason,
        "id": b.id,
        "subdomain": b.subdomain,
        "site_url": site_url(b.subdomain, settings) if b.subdomain else None,
        "status": b.status,
        "practice": b.practice,
        "public": is_public(b) and not b.paused,  # false = only the owner sees it, through the preview
        "live_url": live_url(session, settings, b),  # S19D: "View shop" on My shops; None = practice/draft (preview only)
        "confirm_new": live_contact.waiting(b),  # S19D: "whatsapp"/"upi" changed on a live shop; customers see the old one
        "owner_email": owners[0] if owners else "",  # the sign-in address orders and alerts go to
        # S19D: while an edit waits for the team she keeps working on HER version; customers see profile_json
        "profile": json.loads(b.pending_profile_json or b.profile_json),
        "pending_edit": {"reason": b.pending_reason, "at": b.pending_at.replace(tzinfo=None).isoformat() + "Z"
                         if b.pending_at else None} if b.pending_profile_json else None,
        "theme": theme_out(b),
        "description": b.description,  # S17: her own words, so Describe can open with them again
        "price_list": b.price_list_text,
    }


def live_url(session: Session | None, settings: Settings, b: Business) -> str | None:
    """The shop's real public address, only for a real launched shop (paused or held too: its own page says so).
    Built here from the launch plan / subdomain and APP_DOMAIN, never from anything typed. Practice and draft
    shops are not on the internet, so they get None and the owner uses the private preview."""
    if not is_public(b):
        return None
    if session is not None:
        from app.agents.launch_check import latest_launched_plan

        plan = latest_launched_plan(session, b.id)
        if plan is not None and plan.mode == "full" and plan.site_host:
            return f"https://{plan.site_host}/"
    return site_url(b.subdomain, settings) if b.subdomain else None


def theme_out(b: Business) -> dict:
    """The look this shop is drawn with (S14): the valid choice on the profile, else the rule-based one."""
    profile = Profile.model_validate_json(b.profile_json)
    theme, accent = themes.resolve(profile)
    motif, art = motifs.signature(theme.key, profile.name, profile.motif, profile.art)
    return {"key": theme.key, "accent": accent.key, "suggested": themes.rule_choice(profile),
            "chosen": bool(themes.clean_theme_key(profile.theme)),
            # S20: the shop's signature, drawn by code from keys only (live thumbnails for the picker)
            "motif": motif, "art": art, "motif_chosen": bool(motifs.clean_motif(theme.key, profile.motif)),
            "art_chosen": bool(motifs.clean_arrangement(profile.art)),
            "motifs": motifs.thumbnails(theme.key, profile.name, art),
            "arts": motifs.arrangement_thumbnails(motif, profile.name)}


@router.get("/themes")
def theme_catalog() -> list[dict]:
    """The six shop themes and their accents (for the Review page's picker)."""
    return themes.catalog()


class ThemeChoice(BaseModel):
    theme: str
    accent: str = ""


class SignatureChoice(BaseModel):
    motif: str = ""
    art: str = ""


@router.put("/businesses/{business_id}/signature")
def set_signature(body: SignatureChoice, actor: ActorDep, b: Annotated[Business, Depends(require_business_access)],
                  settings: Annotated[Settings, Depends(get_settings)],
                  session: Annotated[Session, Depends(get_session)]) -> dict:
    """S20: the owner's choice of motif and arrangement. Keys from the fixed lists only; saved on the profile and audited."""
    profile = Profile.model_validate_json(b.profile_json)
    theme = themes.resolve(profile)[0]
    motif, art = motifs.clean_motif(theme.key, body.motif), motifs.clean_arrangement(body.art)
    if (body.motif.strip() and not motif) or (body.art.strip() and not art):
        raise HTTPException(status_code=422, detail="Please pick one of the choices on the list.")
    before = "/".join(motifs.signature(theme.key, profile.name, profile.motif, profile.art))
    profile.motif, profile.art = (motif or profile.motif), (art or profile.art)
    if profile.theme:
        profile.motif = motifs.clean_motif(theme.key, profile.motif)
    b.profile_json = profile.model_dump_json()
    if b.pending_profile_json:
        pending = Profile.model_validate_json(b.pending_profile_json)
        pending.motif, pending.art = profile.motif, profile.art
        b.pending_profile_json = pending.model_dump_json()
    session.add(b)
    session.commit()
    session.refresh(b)
    audit.record(session, actor="owner", action="signature_changed", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=actor.user_id,
                 detail=f"{before} -> {'/'.join(motifs.signature(theme.key, profile.name, profile.motif, profile.art))}")
    return business_out(b, settings, session)


@router.put("/businesses/{business_id}/theme")
def set_theme(body: ThemeChoice, actor: ActorDep, b: Annotated[Business, Depends(require_business_access)],
              settings: Annotated[Settings, Depends(get_settings)],
              session: Annotated[Session, Depends(get_session)]) -> dict:
    """The owner's choice of look. Only keys from the fixed lists are accepted; saved on the profile and audited."""
    key = themes.clean_theme_key(body.theme)
    if not key:
        raise HTTPException(status_code=422, detail="Please pick one of the looks on the list.")
    accent = themes.clean_accent_key(key, body.accent)
    if body.accent.strip() and not accent:
        raise HTTPException(status_code=422, detail="That colour isn't one of this look's colours.")
    profile = Profile.model_validate_json(b.profile_json)
    before = f"{themes.resolve(profile)[0].key}/{themes.resolve(profile)[1].key}"
    profile.theme, profile.accent = key, accent
    profile.motif = motifs.clean_motif(key, profile.motif)  # S20: a motif belongs to one theme
    b.profile_json = profile.model_dump_json()
    if b.pending_profile_json:  # S19D: a held edit keeps the look she just picked when the team publishes it
        pending = Profile.model_validate_json(b.pending_profile_json)
        pending.theme, pending.accent = key, accent
        b.pending_profile_json = pending.model_dump_json()
    session.add(b)
    session.commit()
    session.refresh(b)
    after = f"{key}/{themes.THEMES[key].accent(accent).key}"
    audit.record(session, actor="owner", action="theme_changed", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=actor.user_id, detail=f"{before} -> {after}")
    return business_out(b, settings, session)


NOT_SUPPORTED_DEFAULT = ("Your customers book a time with you, and for now we can only build shops that take orders, "
                         "so we can't make your website yet.")

@router.get("/samples")
def samples() -> list[dict]:
    """The three sample seller inputs, so the 'Try an example' buttons can fill the form."""
    out = []
    for path in sorted(SELLERS.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        out.append({"id": d["id"], "owner_name": d["owner_name"], "city": d["city"],
                    "description": d["description"], "price_list": d["price_list"]})
    return out


def check_describe_limits(session: Session, settings: Settings, actor, visitor: str) -> None:
    """Each Claude reading counts, for a new shop or (S17) reading one again: per user, else per visitor."""
    admin, user = actor.is_admin, actor.user
    if user is not None and not admin:
        if user_describes_today(session, user.id) >= settings.user_describes_per_day:
            raise HTTPException(status_code=429, detail="You've described several shops today already. "
                                "Please come back tomorrow to try another one.")
        # One row per Claude call, not tied to a shop, so deleting the shop doesn't reset the daily cap.
        audit.record(session, actor="reader", action="describe_used", result="ok", user_id=user.id)
    elif not admin and describes_today(session, visitor) >= settings.visitor_describes_per_day:
        raise HTTPException(status_code=429, detail="You've set up several shops today already. "
                            "Please come back tomorrow to try another one.")


async def read_words(session: Session, claude: Claude, actor, description: str, price_list: str,
                     photo: UploadFile | None) -> tuple[Profile, tuple[bytes, str] | None]:
    """The Reader on her words (and menu photo). Plain errors; a booking business is refused (v1 takes orders)."""
    image = None
    if photo is not None and photo.filename:
        data = await photo.read(MAX_IMAGE_BYTES + 1)
        image = (data, (photo.content_type or "").lower())
    try:
        profile = read_business(claude, description=description, price_list=price_list, image=image)
    except ReaderError as e:
        audit.record(session, actor="reader", action="read_business", result="failed", detail=str(e)[:300],
                     user_id=actor.user_id)
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ClaudeBudgetExceeded as e:
        audit.record(session, actor="reader", action="read_business", result="blocked", detail=str(e))
        raise HTTPException(status_code=503, detail="Our assistant has reached today's limit. Please try again tomorrow.") from e
    if profile.kind == "appointments":
        # Scope guard: v1 builds shops that take orders. Don't build a shop for a booking business.
        reason = profile.not_supported_reason.strip() or NOT_SUPPORTED_DEFAULT
        audit.record(session, actor="reader", action="read_business", result="refused",
                     detail="needs appointments/booking, not orders; no shop built")
        raise HTTPException(status_code=422, detail=reason)
    return profile, image


def _empty(v) -> bool:
    return v is None or (isinstance(v, (str, list, dict)) and not v)


def merge_reading(old: Profile, new: Profile, owner_picked_look: bool) -> Profile:
    """S17 "Read it again": the fresh reading wins wherever it found something; a field it left empty keeps what she
    had (her WhatsApp, UPI, delivery areas...). A look she picked herself on Review stays hers."""
    data = new.model_dump()
    for name, value in old.model_dump().items():
        if _empty(data.get(name)) and not _empty(value):
            data[name] = value
    if owner_picked_look:
        data["theme"], data["accent"] = old.theme, old.accent
    return Profile.model_validate(data)


@router.post("/businesses/{business_id}/reread")
async def reread_business(
    request: Request,
    actor: ActorDep,
    b: Annotated[Business, Depends(require_business_access)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    claude: Annotated[Claude, Depends(get_claude)],
    description: Annotated[str, Form(max_length=4000)] = "",
    price_list: Annotated[str, Form(max_length=4000)] = "",
    photo: Annotated[UploadFile | None, File()] = None,
) -> dict:
    """S17: back to Describe. Read her (changed) words again for THIS shop: same address, no second shop. Only before
    launch (after it, details change on Review). Same daily limit as describing a shop."""
    running = session.exec(select(Plan.id).where(Plan.business_id == b.id,
                                                 Plan.status.in_(("approved", "running")))).first()
    if b.status == "live" or running is not None:
        raise HTTPException(status_code=409, detail="Your shop is already launched, so it can't be read again from "
                            "scratch. Change its details on the Review page instead.")
    check_describe_limits(session, settings, actor, visitor_id(request))
    new, image = await read_words(session, claude, actor, description, price_list, photo)
    old = Profile.model_validate_json(b.profile_json)
    picked = session.exec(select(AuditEvent.id).where(AuditEvent.business_id == b.id,
                                                      AuditEvent.action == "theme_changed")).first() is not None
    merged = merge_reading(old, new, picked)
    from app import photos

    photos.remap_items(session, b.id, [p.name for p in merged.products])
    reset_confirmations(b, merged)
    b.name, b.description, b.price_list_text = merged.name, description, price_list
    b.profile_json = merged.model_dump_json()
    session.add(b)
    session.commit()
    session.refresh(b)
    audit.record(session, actor="reader", action="read_business", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=actor.user_id,
                 detail=f"read again: {len(merged.products)} products" + (", with photo" if image else ""))
    fell_back = getattr(claude, "fell_back", False)
    if fell_back:
        audit.record(session, actor="reader", action="claude_fallback", target=f"business:{b.id}", result="ok",
                     business_id=b.id, detail="live Claude unavailable or daily cap reached; used a saved sample")
    return {**business_out(b, settings, session), "assistant_note": FALLBACK_NOTE if fell_back else None}


@router.post("/businesses", status_code=201)
async def create_business(
    request: Request,
    response: Response,
    actor: ActorDep,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    claude: Annotated[Claude, Depends(get_claude)],
    description: Annotated[str, Form(max_length=4000)] = "",
    price_list: Annotated[str, Form(max_length=4000)] = "",
    photo: Annotated[UploadFile | None, File()] = None,
) -> dict:
    visitor = visitor_id(request)
    admin, user = actor.is_admin, actor.user
    if user is not None and not admin and accounts.shops_of(session, user.id) >= settings.max_shops_per_user:
        raise HTTPException(status_code=409, detail=f"You already have {settings.max_shops_per_user} shops, which is "
                            "the most one account can have. Delete one you don't need to make another.")
    check_describe_limits(session, settings, actor, visitor)
    profile, image = await read_words(session, claude, actor, description, price_list, photo)

    # Every shop starts as practice. It becomes real only through an approved user's real launch.
    guest_raw, guest_hash = None, ""
    if user is None:  # "Try it" without signing in: an anonymous cookie owns a practice workspace
        guest_hash = actor.guest
        if not guest_hash:
            guest_raw = secrets.token_urlsafe(32)
            guest_hash = sha(guest_raw)
    b = Business(name=profile.name, description=description, price_list_text=price_list,
                 profile_json=profile.model_dump_json(), subdomain=unique_subdomain(session, slugify(profile.name)),
                 practice=True, guest_hash=guest_hash, visitor="" if admin else visitor)
    session.add(b)
    session.commit()
    session.refresh(b)
    if user is not None:
        session.add(Membership(user_id=user.id, business_id=b.id, role="owner"))
        session.commit()
    audit.record(session, actor="reader", action="read_business", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=actor.user_id,
                 detail=f"{len(profile.products)} products" + (", with photo" if image else "")
                 + (", guest practice" if user is None else ", practice"))
    fell_back = getattr(claude, "fell_back", False)
    if fell_back:
        audit.record(session, actor="reader", action="claude_fallback", target=f"business:{b.id}", result="ok",
                     business_id=b.id, detail="live Claude unavailable or daily cap reached; used a saved sample")
    out = {**business_out(b, settings, session), "assistant_note": FALLBACK_NOTE if fell_back else None}
    if guest_raw is not None:
        accounts.set_guest_cookie(response, settings, guest_raw)
        out["csrf"] = csrf_for(guest_raw)  # the page needs it for its next change (the cookie itself is HttpOnly)
    return out


@router.get("/businesses")
def list_businesses(actor: ActorDep, settings: Annotated[Settings, Depends(get_settings)],
                    session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    """"My shops": only the caller's own, filtered in the query. (The team's list of every shop is /api/admin/businesses.)"""
    if actor.user is not None:
        q = select(Business).join(Membership, Membership.business_id == Business.id).where(Membership.user_id == actor.user.id)
    elif actor.guest:
        q = select(Business).where(Business.guest_hash == actor.guest)
    else:
        return []
    return [{**business_out(b, settings, session), "renewal": shop_renewal(session, settings, b),
             "new_orders": new_orders(session, b.id)}
            for b in session.exec(q.order_by(Business.id.desc())).all()]


def new_orders(session: Session, business_id: int) -> int:
    """Customer orders the owner hasn't confirmed or cancelled yet (test orders never count)."""
    return session.exec(select(func.count()).select_from(Order).where(
        Order.business_id == business_id, Order.is_test == False, Order.status == "new")).one()  # noqa: E712


def shop_renewal(session: Session, settings: Settings, b: Business) -> dict | None:
    """The renewal of a live shop that needs attention soonest (S10 Renewals), for "My shops"."""
    if b.status != "live":
        return None
    from app import renewals
    from app.agents.launch_check import latest_launched_plan
    from app.models import CheckRun

    plan = latest_launched_plan(session, b.id)
    run = session.exec(select(CheckRun).where(CheckRun.business_id == b.id, CheckRun.status == "done")
                       .order_by(CheckRun.id.desc())).first()
    if plan is None:
        return None
    return renewals.nearest(renewals.card(settings, plan.mode, plan.zone, json.loads(run.info_json) if run else {}))


@router.get("/businesses/{business_id}")
def read_one(b: Annotated[Business, Depends(require_business_access)],
             settings: Annotated[Settings, Depends(get_settings)],
             session: Annotated[Session, Depends(get_session)]) -> dict:
    return business_out(b, settings, session)


class ProfileUpdate(BaseModel):
    profile: Profile
    subdomain: str


@router.put("/businesses/{business_id}")
def update_business(body: ProfileUpdate, actor: ActorDep, b: Annotated[Business, Depends(require_business_access)],
                    settings: Annotated[Settings, Depends(get_settings)],
                    session: Annotated[Session, Depends(get_session)],
                    claude: Annotated[Claude, Depends(get_claude)]) -> dict:
    sub = body.subdomain.strip().lower()
    problem = slug_problem(sub) if sub != b.subdomain else None
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if sub != b.subdomain and is_public(b):
        raise HTTPException(status_code=409, detail="Your shop is live at this address, so it can't be changed here.")
    taken = session.exec(select(Business.id).where(Business.subdomain == sub, Business.id != b.id)).first()
    if taken:
        raise HTTPException(status_code=409, detail="That site address is already taken. Please pick another.")
    from app.sites import fulfilment as ful

    if problem := ful.areas_error(body.profile.delivery_areas) if body.profile.selling_mode.endswith("local") else None:
        raise HTTPException(status_code=422, detail=problem)
    old_sub = b.subdomain
    from app.sites import newness
    from app.sites.fulfilment import today_ist

    day = today_ist()
    for item in body.profile.products:  # S19D: a real date, never more than NEW_BADGE_DAYS ahead
        item.new_until = newness.clean(item.new_until, day)
    b.subdomain = sub
    held = edit_hold(b, body.profile, settings, claude)
    if held is not None:  # S19D: the live shop keeps its approved version; this edit waits for the team
        b.pending_profile_json, b.pending_reason, b.pending_at = body.profile.model_dump_json(), held.reason, utcnow()
        session.add(b)
        session.commit()
        session.refresh(b)
        audit.record(session, actor="policy", action="edit_held", target=f"business:{b.id}", result="held",
                     business_id=b.id, user_id=actor.user_id,
                     detail=f"by {held.by}: {held.reason} (fields: {', '.join(changed_fields(b, body.profile)) or 'none'})"[:300])
        return business_out(b, settings, session)
    apply_profile(session, b, body.profile, actor="owner", user_id=actor.user_id,
                  note=f"subdomain {old_sub} -> {sub}" if old_sub != sub else "")
    return business_out(b, settings, session)


def changed_fields(b: Business, new: Profile) -> list[str]:
    """Which profile fields an edit changes (names only: never the values, so no customer or contact data in the log)."""
    old = json.loads(b.profile_json or "{}")
    return sorted(k for k, v in new.model_dump().items() if old.get(k) != v)


def edit_hold(b: Business, new: Profile, settings: Settings, claude: Claude):
    """S19D: a real live shop's edited words go through the go-live policy check again. Returns the Verdict when the
    edit must wait for the team, else None. Fails closed (Claude unavailable -> held), like the launch check; on a real
    server running saved Claude answers every text edit waits for the team (the saved answer would always say OK)."""
    from app.agents.policy import Verdict, policy_check, shop_text
    from app.selfcheck import fixture_on_real_server

    if not live_contact.is_real_live(b):
        return None
    if shop_text(Profile.model_validate_json(b.profile_json)) == shop_text(new):
        return None  # no words changed (prices, photos, hours, the New badge...): nothing to check
    if fixture_on_real_server(settings):
        return Verdict(False, "Our team looks at changes to a live shop's words before they go up.", by="fixture")
    verdict = policy_check(claude, new)
    return None if verdict.ok else verdict


def apply_profile(session: Session, b: Business, new: Profile, actor: str, user_id: int | None, note: str = "") -> None:
    """Save a profile as the shop's own (the owner's save, or the team publishing a held edit), with every follow-up:
    photos follow renamed items, confirmed WhatsApp/UPI kept for customers, confirmations reset, audit rows."""
    from app import photos

    old = Profile.model_validate_json(b.profile_json)
    fields = changed_fields(b, new)
    kept = live_contact.keep_confirmed(b, old, new)
    reset = reset_confirmations(b, new)
    photos.follow_items(session, b.id, [p.name for p in old.products], [p.name for p in new.products])
    old_look, new_look = themes.resolve(old), themes.resolve(new)
    b.name = new.name
    b.profile_json = new.model_dump_json()
    b.pending_profile_json, b.pending_reason, b.pending_at = "", "", None
    session.add(b)
    session.commit()
    session.refresh(b)
    detail = "; ".join(x for x in (note, f"fields: {', '.join(fields)}" if fields else "") if x)
    audit.record(session, actor=actor, action="profile_saved", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=user_id, detail=detail[:300])
    if (old_look[0].key, old_look[1].key) != (new_look[0].key, new_look[1].key):
        audit.record(session, actor=actor, action="theme_changed", target=f"business:{b.id}", result="ok",
                     business_id=b.id, user_id=user_id,
                     detail=f"{old_look[0].key}/{old_look[1].key} -> {new_look[0].key}/{new_look[1].key}")
    for what in reset:
        audit.record(session, actor="system", action="confirmation_reset", target=f"business:{b.id}", result="ok",
                     business_id=b.id, user_id=user_id, detail=f"{what} changed: please check it again"
                     + (" (customers still see the confirmed one)" if kept else ""))


def reset_confirmations(b: Business, new: Profile) -> list[str]:
    """A changed WhatsApp number or UPI ID / name undoes the owner's confirmation of the old one."""
    out = []
    if b.wa_confirmed and b.wa_confirmed != new.whatsapp:
        b.wa_confirmed, b.wa_confirmed_at = "", None
        out.append("WhatsApp number")
    if b.upi_confirmed and b.upi_confirmed != golive.upi_key(new):
        b.upi_confirmed, b.upi_confirmed_at = "", None
        out.append("UPI ID or name")
    return out


def is_own(session: Session, actor, b: Business) -> bool:
    """The caller OWNS this shop (not just may see it, as the team may)."""
    if actor.token_admin:
        return False
    if actor.user is not None:
        return session.exec(select(Membership.id).where(Membership.user_id == actor.user.id,
                                                        Membership.business_id == b.id)).first() is not None
    return bool(actor.guest) and b.guest_hash == actor.guest


@router.get("/businesses/{business_id}/golive")
def golive_checklist(b: Annotated[Business, Depends(require_business_access)],
                     session: Annotated[Session, Depends(get_session)]) -> dict:
    """What's still needed before a real launch, in plain words, plus the owner's two checks:
    "Test this number" (a wa.me link to her own number) and the Rs 1 UPI test (her shop's real UPI QR for Rs 1)."""
    profile = Profile.model_validate_json(b.profile_json)
    res = golive.out(session, b)
    res["whatsapp"] = profile.whatsapp
    res["whatsapp_test_url"] = f"https://wa.me/{profile.whatsapp.lstrip('+')}" if profile.whatsapp else None
    uri = upi_uri(profile, amount_inr=1) if profile.upi_id else None
    res["upi_test"] = {"uri": uri, "qr_svg": str(upi_qr_svg(uri)), "name": profile.upi_display_name} if uri else None
    res["confirmed"] = {"whatsapp_at": iso(b.wa_confirmed_at) if golive.whatsapp_confirmed(b, profile) else None,
                        "upi_at": iso(b.upi_confirmed_at) if golive.upi_confirmed(b, profile) else None,
                        "own_goods_at": iso(b.own_goods_at), "terms_at": iso(b.terms_at),
                        "previewed_at": iso(b.previewed_at)}
    return res


def iso(when) -> str | None:
    return when.replace(tzinfo=None).isoformat() + "Z" if when else None


class Confirmation(BaseModel):
    what: Literal["whatsapp", "upi", "agreements"]
    own_goods: bool = False
    terms: bool = False


@router.post("/businesses/{business_id}/confirm")
def confirm(body: Confirmation, actor: ActorDep, b: Annotated[Business, Depends(require_business_access)],
            session: Annotated[Session, Depends(get_session)]) -> dict:
    """The owner's own checks, stored as "confirmed by you" (never "verified"): her WhatsApp number opens her chat;
    her UPI app shows her name for the shop's UPI ID; she makes/sells these herself and accepts the Terms.
    Only the shop's owner may confirm: anyone else, the team included, gets 404."""
    if not is_own(session, actor, b):
        raise HTTPException(status_code=404, detail="We couldn't find that shop.")
    profile = Profile.model_validate_json(b.profile_json)
    now = utcnow()
    if body.what == "whatsapp":
        if not profile.whatsapp:
            raise HTTPException(status_code=422, detail="Please add your WhatsApp number and save first.")
        b.wa_confirmed, b.wa_confirmed_at = profile.whatsapp, now
        live_contact.confirmed(b, live_contact.WA)  # S19D: customers see the new number from now on
        detail = "WhatsApp number confirmed by the owner (opens her chat)"
    elif body.what == "upi":
        if not (profile.upi_id and profile.upi_display_name.strip()):
            raise HTTPException(status_code=422,
                                detail="Please add your UPI ID and the name your UPI app shows, and save first.")
        b.upi_confirmed, b.upi_confirmed_at = golive.upi_key(profile), now
        live_contact.confirmed(b, live_contact.UPI)
        detail = "UPI name test: the owner saw the expected name in her own UPI app"
    else:
        if not (body.own_goods and body.terms):
            raise HTTPException(status_code=422, detail="Please tick both boxes.")
        b.own_goods_at, b.terms_at = now, now
        detail = "owner: makes/sells these herself and may sell them; accepted the Terms"
    session.add(b)
    session.commit()
    session.refresh(b)
    audit.record(session, actor=actor.label, action=f"owner_confirmed_{body.what}", target=f"business:{b.id}",
                 result="ok", business_id=b.id, user_id=actor.user_id, detail=detail)
    return golive_checklist(b, session)


@router.get("/businesses/{business_id}/preview", response_class=HTMLResponse)
def preview(b: Annotated[Business, Depends(require_business_access)], actor: ActorDep,
            session: Annotated[Session, Depends(get_session)], page: str = "home",
            inline: bool = False) -> HTMLResponse:
    """The owner's private look at their shop (drafts and practice shops are never public). The owner's first
    look is recorded for the go-live checklist (the team looking doesn't count)."""
    if b.previewed_at is None and not inline and is_own(session, actor, b):  # inline: the Review page's look picker
        b.previewed_at = utcnow()
        session.add(b)
        session.commit()
        session.refresh(b)
        audit.record(session, actor=actor.label, action="preview_opened", target=f"business:{b.id}", result="ok",
                     business_id=b.id, user_id=actor.user_id, detail="first look (go-live checklist)")
    profile = Profile.model_validate_json(b.profile_json)
    from app import photos
    from app.sites.orders import full_days

    return HTMLResponse(render_site(profile, page="privacy" if page == "privacy" else "home", preview=True,
                                    photos=photos.for_site(session, b.id), full_dates=full_days(session, b, profile)),
                        headers={"X-Robots-Tag": "noindex", "Cache-Control": "no-store"})


def claim_out(c) -> dict | None:
    """S20: what a customer SAID about paying, for the owner only. Always a claim ("says paid"), never "paid"."""
    from app.payclaims import show_utr

    if c is None:
        return None
    return {"utr": show_utr(c.utr), "has_screenshot": bool(c.screenshot),
            "says": f"Customer says paid \u00b7 UTR {show_utr(c.utr)}",
            "at": c.updated_at.replace(tzinfo=None).isoformat() + "Z"}


def order_out(o: Order, shop_name: str, claim=None) -> dict:
    """One order for its owner. The full phone number and the delivery address are shown here, to the owner only (audit logs
    never hold them, and neither does the shared report)."""
    from app.sites import fulfilment as ful

    return {"fulfilment": o.fulfilment, "delivery_address": o.delivery_address, "delivery_pin": o.delivery_pin,
            "wanted_date": o.wanted_date, "time_slot": o.time_slot, "fee_inr": o.fee_inr, "pay_now_inr": o.pay_now_inr,
            "pay_later_inr": o.pay_later_inr, "payment_terms": o.payment_terms,
            "payment_label": ful.payment_label(o.payment_terms, o.status, o.pay_now_inr, o.pay_later_inr, o.total_inr),
            "paid_action": ful.paid_action_label(o.payment_terms),
            "id": o.id, "ref": o.ref, "is_test": o.is_test, "customer_name": o.customer_name,
            "customer_phone": o.customer_phone, "items": json.loads(o.items_json), "total_inr": o.total_inr,
            "note": o.note, "email_status": o.email_status, "status": o.status,
            "next_statuses": list(STATUS_STEPS.get(o.status, ())),
            "whatsapp_url": customer_whatsapp_link(shop_name, o), "tel_url": tel_link(o.customer_phone) or None,
            "payment_claim": claim_out(claim),
            "created_at": o.created_at.replace(tzinfo=None).isoformat() + "Z"}


@router.get("/businesses/{business_id}/orders")
def list_orders(b: Annotated[Business, Depends(require_business_access)],
                session: Annotated[Session, Depends(get_session)], tests: bool = False) -> list[dict]:
    """The shop's orders, newest first. The checker's own test orders are left out unless asked for."""
    q = select(Order).where(Order.business_id == b.id)
    if not tests:
        q = q.where(Order.is_test == False)  # noqa: E712
    rows = session.exec(q.order_by(Order.id.desc()).limit(500)).all()
    claims = {c.order_id: c for c in session.exec(select(PaymentClaim).where(PaymentClaim.business_id == b.id)).all()}
    return [order_out(o, b.name, claims.get(o.id)) for o in rows]


@router.get("/businesses/{business_id}/orders/{order_id}/payment-screenshot")
def payment_screenshot(order_id: int, request: Request, b: Annotated[Business, Depends(require_business_access)],
                       settings: Annotated[Settings, Depends(get_settings)],
                       session: Annotated[Session, Depends(get_session)]) -> Response:
    """S20: the screenshot a customer attached to "I've paid". Only the owner (the gate above), only on the app's own host
    (never a shop host), never cached. Another shop's order, a test order or an order without one all answer 404."""
    from app.sites.hosts import normalize_host, subdomain_label

    if subdomain_label(normalize_host(request.headers.get("host", "")), settings) is not None:
        raise HTTPException(status_code=404)
    claim = session.exec(select(PaymentClaim).where(PaymentClaim.order_id == order_id,
                                                    PaymentClaim.business_id == b.id)).first()
    if claim is None or not claim.screenshot:
        raise HTTPException(status_code=404, detail="There is no screenshot for that order.")
    return Response(claim.screenshot, media_type="image/webp",
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                             "Content-Security-Policy": "default-src 'none'; sandbox", "X-Robots-Tag": "noindex"})


class StatusChange(BaseModel):
    status: Literal["confirmed", "paid", "done", "cancelled"]


@router.post("/businesses/{business_id}/orders/{order_id}/status")
def set_order_status(order_id: int, body: StatusChange, actor: ActorDep,
                     b: Annotated[Business, Depends(require_business_access)],
                     session: Annotated[Session, Depends(get_session)]) -> dict:
    """The owner moves one of her orders on (New → Confirmed → Paid → Done, or Cancelled). Audited.
    Another shop's order, or a test order, answers 404 like an order that doesn't exist."""
    o = session.exec(select(Order).where(Order.id == order_id, Order.business_id == b.id,
                                         Order.is_test == False)).first()  # noqa: E712
    if o is None:
        raise HTTPException(status_code=404, detail="We couldn't find that order.")
    if not can_move(o.status, body.status):
        raise HTTPException(status_code=409, detail=f"An order that is {STATUS_LABELS[o.status].lower()} can't be "
                            f"marked {STATUS_LABELS[body.status].lower()}.")
    old, o.status, o.status_changed_at = o.status, body.status, utcnow()
    session.add(o)
    session.commit()
    session.refresh(o)
    audit.record(session, actor=actor.label, action="order_status", target=f"order:{o.id}", result="ok",
                 business_id=b.id, user_id=actor.user_id, detail=f"{o.ref}: {old} -> {o.status}")
    from app import payclaims

    return order_out(o, b.name, payclaims.claim_for(session, o.id))


@router.get("/businesses/{business_id}/export")
def export_business(b: Annotated[Business, Depends(require_business_access)],
                    session: Annotated[Session, Depends(get_session)]) -> dict:
    """Everything we hold about the shop, for the owner to keep."""
    return {"shop": {"name": b.name, "address": b.subdomain, "status": b.status, "practice": b.practice,
                     "created_at": b.created_at.isoformat(), "description": b.description,
                     "price_list": b.price_list_text, "profile": json.loads(b.profile_json)},
            "orders": list_orders(b, session, tests=True)}


@router.delete("/businesses/{business_id}")
def delete_business(actor: ActorDep, b: Annotated[Business, Depends(require_business_access)],
                    settings: Annotated[Settings, Depends(get_settings)],
                    session: Annotated[Session, Depends(get_session)],
                    server: Annotated[Integrations, Depends(get_integrations)],
                    practice: Annotated[Integrations, Depends(get_practice_integrations)]) -> dict:
    """Take the shop off the internet and delete it with its orders. Can't be undone."""
    business_id, was_public = b.id, is_public(b)
    purge_business(session, settings, for_business(b, server, practice), b)
    audit.record(session, actor=actor.label, action="shop_deleted", target=f"business:{business_id}", result="ok",
                 user_id=actor.user_id, detail="was public" if was_public else "was not public")
    return {"ok": True}


# ---------- product photos (S12): upload on the Review step ----------

PHOTO_UPLOADS_PER_DAY = 60  # per shop: re-encoding costs CPU on the one app process


def photo_list(session: Session, b: Business) -> dict:
    from app import photos

    site = photos.for_site(session, b.id)
    return {"shop": site["shop"], "items": site["items"], "max_shop": photos.MAX_SHOP_PHOTOS,
            "max_mb": photos.MAX_UPLOAD_BYTES // (1024 * 1024)}


@router.get("/businesses/{business_id}/photos")
def list_photos(b: Annotated[Business, Depends(require_business_access)],
                session: Annotated[Session, Depends(get_session)]) -> dict:
    return photo_list(session, b)


@router.post("/businesses/{business_id}/photos", status_code=201)
async def upload_photo(b: Annotated[Business, Depends(require_business_access)], actor: ActorDep,
                       session: Annotated[Session, Depends(get_session)],
                       file: Annotated[UploadFile, File()], item: Annotated[str, Form(max_length=120)] = "",
                       alt: Annotated[str, Form(max_length=200)] = "",
                       item_hint: Annotated[str, Form(max_length=200)] = "") -> dict:
    """One photo: for the shop (item "") or for one of its items (by the item's name). Checked by content, re-encoded,
    stripped (app/photos.py). Audited without the image itself.
    S17 `item_hint`: what the seller typed in a row of her list on the Describe step, before the Reader tidied the
    name. The server finds the item(s) made from it (photos.match_item); no match is a plain refusal, nothing stored."""
    from datetime import timedelta

    from app import photos

    profile = Profile.model_validate_json(b.profile_json)
    names = [p.name for p in profile.products]
    if item and item not in names:
        raise HTTPException(status_code=422, detail="That item isn't on your list any more. Refresh the page.")
    targets = [item.strip()] if item else (photos.match_item(item_hint, names) if item_hint.strip() else [""])
    if not targets:
        raise HTTPException(status_code=422, detail=f"We couldn't find “{item_hint.strip()[:60]}” on your list. "
                            "Add its photo on the next page, next to the item.")
    recent = session.exec(select(AuditEvent.id).where(
        AuditEvent.business_id == b.id, AuditEvent.action == "photo_added",
        AuditEvent.created_at >= utcnow() - timedelta(days=1))).all()
    if len(recent) >= PHOTO_UPLOADS_PER_DAY:
        raise HTTPException(status_code=429, detail="That's a lot of photos for one day. Please try again tomorrow.")
    data = await file.read(photos.MAX_UPLOAD_BYTES + 1)
    for target in targets:  # one item, or (S17) each size of the item she named without a size
        try:
            row = photos.add(session, b.id, data, item=target, alt=alt.strip() or (target or profile.name))
        except photos.PhotoRefused as e:
            audit.record(session, actor=actor.label, action="photo_refused", target=f"business:{b.id}",
                         result="refused", business_id=b.id, user_id=actor.user_id, detail=str(e)[:200])
            raise HTTPException(status_code=422, detail=str(e)) from None
        audit.record(session, actor=actor.label, action="photo_added", target=f"photo:{row.id}", result="ok",
                     business_id=b.id, user_id=actor.user_id,
                     detail=f"{'item' if row.item else 'shop'} photo, {len(row.small) + len(row.large)} bytes after "
                            "re-encoding" + (" (matched from the Describe list)" if item_hint.strip() and not item else ""))
    return photo_list(session, b) | {"matched": [t for t in targets if t]}


@router.delete("/businesses/{business_id}/photos/{photo_id}")
def delete_photo(photo_id: int, b: Annotated[Business, Depends(require_business_access)], actor: ActorDep,
                 session: Annotated[Session, Depends(get_session)]) -> dict:
    from app.models import Photo

    row = session.get(Photo, photo_id)
    if row is None or row.business_id != b.id:
        raise HTTPException(status_code=404, detail="We couldn't find that photo.")
    session.delete(row)
    session.commit()
    audit.record(session, actor=actor.label, action="photo_removed", target=f"photo:{photo_id}", result="ok",
                 business_id=b.id, user_id=actor.user_id)
    return photo_list(session, b)
