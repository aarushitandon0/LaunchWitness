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
from app.models import AuditEvent, Business, Membership, Order, Plan, utcnow
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
from app.sites import themes
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
        "owner_email": owners[0] if owners else "",  # the sign-in address orders and alerts go to
        "profile": json.loads(b.profile_json),
        "theme": theme_out(b),
    }


def theme_out(b: Business) -> dict:
    """The look this shop is drawn with (S14): the valid choice on the profile, else the rule-based one."""
    profile = Profile.model_validate_json(b.profile_json)
    theme, accent = themes.resolve(profile)
    return {"key": theme.key, "accent": accent.key, "suggested": themes.rule_choice(profile),
            "chosen": bool(themes.clean_theme_key(profile.theme))}


@router.get("/themes")
def theme_catalog() -> list[dict]:
    """The six shop themes and their accents (for the Review page's picker)."""
    return themes.catalog()


class ThemeChoice(BaseModel):
    theme: str
    accent: str = ""


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
    b.profile_json = profile.model_dump_json()
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
    if user is not None and not admin:
        if accounts.shops_of(session, user.id) >= settings.max_shops_per_user:
            raise HTTPException(status_code=409, detail=f"You already have {settings.max_shops_per_user} shops, which is "
                                "the most one account can have. Delete one you don't need to make another.")
        if user_describes_today(session, user.id) >= settings.user_describes_per_day:
            raise HTTPException(status_code=429, detail="You've described several shops today already. "
                                "Please come back tomorrow to try another one.")
    elif not admin and describes_today(session, visitor) >= settings.visitor_describes_per_day:
        raise HTTPException(status_code=429, detail="You've set up several shops today already. "
                            "Please come back tomorrow to try another one.")
    if user is not None and not admin:
        # One row per Claude call, not tied to a shop, so deleting the shop doesn't reset the daily cap.
        audit.record(session, actor="reader", action="describe_used", result="ok", user_id=user.id)
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
                    session: Annotated[Session, Depends(get_session)]) -> dict:
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
    reset = reset_confirmations(b, body.profile)
    from app import photos

    photos.follow_items(session, b.id, [p.name for p in Profile.model_validate_json(b.profile_json).products],
                        [p.name for p in body.profile.products])
    old_look = themes.resolve(Profile.model_validate_json(b.profile_json))
    new_look = themes.resolve(body.profile)
    b.name = body.profile.name
    b.profile_json = body.profile.model_dump_json()
    b.subdomain = sub
    session.add(b)
    session.commit()
    session.refresh(b)
    audit.record(session, actor="owner", action="profile_saved", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=actor.user_id, detail=f"subdomain {old_sub} -> {sub}" if old_sub != sub else "")
    if (old_look[0].key, old_look[1].key) != (new_look[0].key, new_look[1].key):
        audit.record(session, actor="owner", action="theme_changed", target=f"business:{b.id}", result="ok",
                     business_id=b.id, user_id=actor.user_id,
                     detail=f"{old_look[0].key}/{old_look[1].key} -> {new_look[0].key}/{new_look[1].key}")
    for what in reset:
        audit.record(session, actor="system", action="confirmation_reset", target=f"business:{b.id}", result="ok",
                     business_id=b.id, user_id=actor.user_id, detail=f"{what} changed: please check it again")
    return business_out(b, settings, session)


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
        detail = "WhatsApp number confirmed by the owner (opens her chat)"
    elif body.what == "upi":
        if not (profile.upi_id and profile.upi_display_name.strip()):
            raise HTTPException(status_code=422,
                                detail="Please add your UPI ID and the name your UPI app shows, and save first.")
        b.upi_confirmed, b.upi_confirmed_at = golive.upi_key(profile), now
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


def order_out(o: Order, shop_name: str) -> dict:
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
            "created_at": o.created_at.replace(tzinfo=None).isoformat() + "Z"}


@router.get("/businesses/{business_id}/orders")
def list_orders(b: Annotated[Business, Depends(require_business_access)],
                session: Annotated[Session, Depends(get_session)], tests: bool = False) -> list[dict]:
    """The shop's orders, newest first. The checker's own test orders are left out unless asked for."""
    q = select(Order).where(Order.business_id == b.id)
    if not tests:
        q = q.where(Order.is_test == False)  # noqa: E712
    rows = session.exec(q.order_by(Order.id.desc()).limit(500)).all()
    return [order_out(o, b.name) for o in rows]


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
    return order_out(o, b.name)


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
