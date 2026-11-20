"""S20: "I've paid". A customer who paid in her own UPI app tells the shop, on the thank-you / status page.

This is a CLAIM and is always worded as one ("says paid"). LaunchWitness never sees a bank, never checks a payment and
never calls an order paid: the owner looks in her own UPI app and marks the order Paid herself (the existing status flow).

What is kept: the 12-digit UPI reference (UTR) and, optionally, ONE screenshot, re-encoded from its pixels as WebP by the
same gate as shop photos (size cap, content sniff, pixel cap, no metadata). Both are private to the owner: never in an
audit row, evidence, the shared report, a log or a public page. They go with the order, the shop or the account, and
30 days after the order is Done or Cancelled (`purge_old`, run by the daily job).
"""

import io
import re
from datetime import timedelta

from PIL import Image
from sqlmodel import Session, delete, func, select

from app import audit, photos
from app.config import Settings
from app.mail.smtp import Mailer
from app.models import Business, Order, PaymentClaim, utcnow
from app.sites.render import format_inr

MAX_SHOT_BYTES = 4 * 1024 * 1024  # a phone screenshot is well under this; the body is refused above it
MAX_BODY_BYTES = MAX_SHOT_BYTES + 64 * 1024  # the whole form
SHOT_WIDTH = 900  # wide enough to read a UPI receipt
KEEP_DAYS = 30  # after the order is Done or Cancelled
SUBMITS_PER_ORDER = 6  # one claim per order; a few corrections allowed
CLAIMS_PER_VISITOR_PER_HOUR = 10
UTR = re.compile(r"^[0-9]{12}$")  # ASCII digits only (\d would accept Arabic-Indic and other Unicode digits)


class ClaimRefused(ValueError):
    """Plain words for the customer."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def parse_utr(text: str) -> str:
    """Exactly 12 digits; spaces (and dashes people copy along) are accepted and dropped."""
    digits = re.sub(r"[\s\-]", "", text or "")
    if not UTR.match(digits):
        raise ClaimRefused("Please enter the 12-digit UPI reference number (UTR) from your payment, for example "
                           "4021 5678 9012. You can find it in your UPI app under the payment.")
    return digits


def show_utr(utr: str) -> str:
    return " ".join(utr[i:i + 4] for i in range(0, len(utr), 4))


REF_PHOTO_BYTES = 5 * 1024 * 1024  # S22: a customer's reference photo (photo cake, design, garment)
REF_BODY_BYTES = REF_PHOTO_BYTES + 128 * 1024  # the whole order form with one photo
HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif")


def process_screenshot(data: bytes) -> tuple[bytes, int, int]:
    return process_image(data, max_bytes=MAX_SHOT_BYTES, word="screenshot")


def process_reference(data: bytes) -> tuple[bytes, int, int]:
    """S22: a custom order's reference photo, through the very same gate as a payment screenshot. iPhone HEIC can't
    be decoded here (no HEIF codec in the image), so it gets its own polite sentence instead of "not a photo"."""
    if data[4:8] == b"ftyp" and data[8:12] in HEIC_BRANDS:
        raise ClaimRefused("This photo is in the iPhone HEIC format, which we can't open. Please choose a JPEG or PNG "
                           "(a screenshot of the photo works), or leave it out and send it to the shop on WhatsApp.")
    return process_image(data, max_bytes=REF_PHOTO_BYTES, word="photo")


def process_image(data: bytes, *, max_bytes: int, word: str) -> tuple[bytes, int, int]:
    """Same gate as shop photos (photos.clean_image), one WebP at SHOT_WIDTH. Nothing of the original survives."""
    try:
        clean = photos.clean_image(data, max_bytes=max_bytes)
    except photos.PhotoRefused as e:
        raise ClaimRefused(str(e).replace("photo", word)) from None
    if clean.width > SHOT_WIDTH:
        clean = clean.resize((SHOT_WIDTH, round(clean.height * SHOT_WIDTH / clean.width)), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    clean.save(out, "WEBP", quality=photos.QUALITY, method=4)  # no exif=, no icc_profile=
    return out.getvalue(), clean.width, clean.height


def order_for_token(session: Session, business: Business, token: str) -> Order | None:
    """The real order behind a status link: this shop's, never a test order, and only for a well-formed token."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{24,64}", token or ""):
        return None
    from app.safety.access import sha

    return session.exec(select(Order).where(Order.business_id == business.id, Order.status_token == sha(token),
                                            Order.is_test == False)).first()  # noqa: E712


def claim_for(session: Session, order_id: int | None) -> PaymentClaim | None:
    if order_id is None:
        return None
    return session.exec(select(PaymentClaim).where(PaymentClaim.order_id == order_id)).first()


def submit(session: Session, settings: Settings, mailer: Mailer, *, business: Business, profile, order: Order,
           utr_text: str, screenshot: bytes | None, visitor: str, channel: str = "smtp") -> PaymentClaim:
    """Store (or replace) the order's claim and tell the owner once. Raises ClaimRefused."""
    if order.is_test:
        raise ClaimRefused("This is a test order.", 404)
    if order.status in ("done", "cancelled"):
        raise ClaimRefused("This order is already closed. Please message the shop if you have a question.", 409)
    if not order.pay_now_inr:
        raise ClaimRefused("There is nothing to pay now for this order.", 409)
    now = utcnow()
    mine = session.exec(select(func.count()).select_from(PaymentClaim).where(
        PaymentClaim.visitor == visitor, PaymentClaim.updated_at >= now - timedelta(hours=1))).one()
    row = claim_for(session, order.id)
    if (row is not None and row.submits >= SUBMITS_PER_ORDER) or (mine >= CLAIMS_PER_VISITOR_PER_HOUR and visitor):
        audit.record(session, actor="customer", action="payment_claim", target=f"order:{order.id}", result="blocked",
                     business_id=business.id, detail="rate limit")
        raise ClaimRefused("You have sent this a few times already. Please message the shop on WhatsApp instead.", 429)
    utr = parse_utr(utr_text)  # after the rate limit: a bad guess still counts as nothing, but never stores anything
    shot = process_screenshot(screenshot) if screenshot else None
    replaced = row is not None
    if row is None:
        row = PaymentClaim(business_id=business.id, order_id=order.id, utr=utr, visitor=visitor)
    else:
        row.utr, row.visitor, row.submits, row.updated_at = utr, visitor, row.submits + 1, now
    row.screenshot, row.screenshot_w, row.screenshot_h = (shot[0], shot[1], shot[2]) if shot else (None, 0, 0)
    session.add(row)
    session.commit()
    session.refresh(row)
    # Audited WITHOUT the UTR or the image: only that a claim came, whether it replaced one, and whether it has a picture.
    audit.record(session, actor="customer", action="payment_claim", target=f"order:{order.id}", result="ok",
                 business_id=business.id,
                 detail=("replaced an earlier claim" if replaced else "customer says paid") + (", with a screenshot" if shot else ""))
    if not replaced:
        notify_owner(session, settings, mailer, business=business, profile=profile, order=order, claim=row, channel=channel)
    return row


def notify_owner(session: Session, settings: Settings, mailer: Mailer, *, business: Business, profile, order: Order,
                 claim: PaymentClaim, channel: str = "smtp") -> None:
    """One email: "Riya says she paid ₹650 for LW-XXXX (UTR ...). Check your UPI app, then mark it Paid." Never for a test order."""
    from app import outbox
    from app.sites.orders import order_recipients

    first = order.customer_name.split()[0] if order.customer_name.split() else "Your customer"
    orders_url = f"{settings.app_base_url.rstrip('/')}/#/b/{business.id}/orders"
    amount = format_inr(order.pay_now_inr)
    subject = f"{first} says they paid {amount} for {order.ref}"
    body = "\n".join([
        f"{order.customer_name} says they paid {amount} for {order.ref} (UTR {show_utr(claim.utr)}).",
        "",
        "This is what the customer told us. LaunchWitness does not see your bank and cannot check it.",
        "Check your UPI app. If the money is there, mark the order Paid:",
        orders_url,
        "",
        "If you can't find it, message the customer (their WhatsApp is on the order) before you send anything."])
    outbox.send(session, settings, mailer, kind="payment_claim", key=f"payclaim:{order.id}",
                to=", ".join(order_recipients(session, settings, business)), subject=subject, body=body, channel=channel,
                business_id=business.id,  # no order_id: the order's own "email sent" status stays about the order email
                ref={"audit": {"actor": "system", "action": "payment_claim_email", "target": f"order:{order.id}"}})


def purge_old(session: Session, now=None) -> int:
    """Claims (UTR + screenshot) of orders that were Done or Cancelled more than KEEP_DAYS ago. Run by the daily job."""
    cutoff = (now or utcnow()) - timedelta(days=KEEP_DAYS)
    ids = session.exec(select(Order.id).where(Order.status.in_(("done", "cancelled")),  # type: ignore[attr-defined]
                                              Order.status_changed_at < cutoff)).all()
    if not ids:
        return 0
    # S22: a custom order's reference photo goes on the same day as the payment note
    old_photos = session.exec(select(Order).where(Order.id.in_(ids), Order.ref_photo != None)).all()  # type: ignore[attr-defined]  # noqa: E711
    for o in old_photos:
        o.ref_photo, o.ref_photo_w, o.ref_photo_h = None, 0, 0
        session.add(o)
    if old_photos:
        session.commit()
        audit.record(session, actor="system", action="reference_photos_purged", result="ok",
                     detail=f"{len(old_photos)} reference photo(s) removed, 30 days after the order closed")
    n = session.exec(select(func.count()).select_from(PaymentClaim).where(
        PaymentClaim.order_id.in_(ids))).one()  # type: ignore[attr-defined]
    if n:
        session.exec(delete(PaymentClaim).where(PaymentClaim.order_id.in_(ids)))  # type: ignore[attr-defined]
        session.commit()
        audit.record(session, actor="system", action="payment_claims_purged", result="ok",
                     detail=f"{n} payment note(s) removed, 30 days after the order closed")
    return n


def purge_job(engine) -> int:
    """The daily job (and once at start-up): opens its own session, never raises into the scheduler."""
    try:
        with Session(engine) as s:
            return purge_old(s)
    except Exception:  # noqa: BLE001  a failed purge is retried tomorrow; it must never stop the scheduler
        return 0
