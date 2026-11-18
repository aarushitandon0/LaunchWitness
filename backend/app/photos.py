"""S12: product photos. Up to MAX_SHOP_PHOTOS per shop plus one per item.

Every upload is: size-capped (MAX_UPLOAD_BYTES, read in chunks so a huge body is never held), type-checked by its
CONTENT (Pillow must decode it as JPEG, PNG or WebP; the file name and the browser's content type are ignored),
refused above MAX_PIXELS (decompression bombs), turned upright from its EXIF orientation, then RE-ENCODED from the
pixels alone as WebP at two widths. Nothing of the original file survives: no EXIF, no GPS location, no comments,
no colour profile, no embedded thumbnail, no trailing bytes.
"""

import io
import re
import secrets
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlmodel import Session, select

from app.models import Photo

MAX_SHOP_PHOTOS = 6
MAX_UPLOAD_BYTES = 7 * 1024 * 1024  # Caddy refuses bodies over 8 MB (deploy/Caddyfile.prod): leave room for the form
MAX_PIXELS = 40_000_000  # about 7,700 x 5,200: more than any phone camera; a bomb is refused, never decoded
MIN_SIDE = 64
ALLOWED = {"JPEG", "PNG", "WEBP"}
SMALL_WIDTH, LARGE_WIDTH = 480, 1200
QUALITY = 80
CACHE = "public, max-age=31536000, immutable"  # the URL changes when the photo does (a new random name)


class PhotoRefused(ValueError):
    """Plain words for the owner."""


def _webp(img: Image.Image, width: int) -> tuple[bytes, int, int]:
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, "WEBP", quality=QUALITY, method=4)  # no exif=, no icc_profile=: nothing but pixels
    return out.getvalue(), img.width, img.height


def process(data: bytes) -> dict:
    """Validate and re-encode one upload. Raises PhotoRefused with a sentence the owner understands."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise PhotoRefused(f"That photo is too big. Please use one under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not data:
        raise PhotoRefused("That file is empty.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(io.BytesIO(data)) as probe:
                fmt = probe.format
                if fmt not in ALLOWED:
                    raise PhotoRefused("Please choose a photo (JPEG, PNG or WebP).")
                if probe.width * probe.height > MAX_PIXELS:
                    raise PhotoRefused("That photo has too many pixels. Please use a smaller one.")
                probe.verify()  # structure check; the image must be opened again to use it
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                img = ImageOps.exif_transpose(img)  # upright, as the phone showed it; the EXIF itself is dropped
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    rgba = img.convert("RGBA")
                    clean = Image.new("RGB", rgba.size, (255, 255, 255))
                    clean.paste(rgba, mask=rgba.split()[3])
                else:
                    clean = img.convert("RGB")
                # copy the pixels into a brand-new image: no info dict, no metadata of any kind travels on
                clean = Image.frombytes("RGB", clean.size, clean.tobytes())
        except PhotoRefused:
            raise
        except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise PhotoRefused("Please choose a photo (JPEG, PNG or WebP).") from None
        except (OSError, SyntaxError, ValueError):
            raise PhotoRefused("We couldn't read that photo. Please try another one.") from None
    if min(clean.size) < MIN_SIDE:
        raise PhotoRefused("That photo is very small. Please use a bigger one.")
    small, sw, sh = _webp(clean, SMALL_WIDTH)
    large, lw, lh = _webp(clean, LARGE_WIDTH)
    return {"small": small, "large": large, "small_w": sw, "small_h": sh, "large_w": lw, "large_h": lh}


def shop_photos(session: Session, business_id: int) -> list[Photo]:
    return list(session.exec(select(Photo).where(Photo.business_id == business_id, Photo.item == "")
                             .order_by(Photo.id)).all())


def item_photos(session: Session, business_id: int) -> dict[str, Photo]:
    rows = session.exec(select(Photo).where(Photo.business_id == business_id, Photo.item != "")
                        .order_by(Photo.id)).all()
    return {p.item: p for p in rows}


def add(session: Session, business_id: int, data: bytes, *, item: str = "", alt: str = "") -> Photo:
    """Adds a shop photo (refused past MAX_SHOP_PHOTOS) or sets an item's photo (replacing the old one)."""
    if not item and len(shop_photos(session, business_id)) >= MAX_SHOP_PHOTOS:
        raise PhotoRefused(f"You already have {MAX_SHOP_PHOTOS} shop photos. Remove one to add another.")
    fields = process(data)
    if item:
        for old in session.exec(select(Photo).where(Photo.business_id == business_id, Photo.item == item)).all():
            session.delete(old)
    photo = Photo(business_id=business_id, item=item, name=secrets.token_hex(16), alt=alt[:200], **fields)
    session.add(photo)
    session.commit()
    session.refresh(photo)
    return photo


def out(p: Photo, base: str = "") -> dict:
    """For the template and the API: the two URLs and sizes (no bytes)."""
    return {"id": p.id, "item": p.item, "alt": p.alt,
            "small": f"{base}/photos/{p.name}-{SMALL_WIDTH}.webp", "large": f"{base}/photos/{p.name}-{LARGE_WIDTH}.webp",
            "small_w": p.small_w, "small_h": p.small_h, "large_w": p.large_w, "large_h": p.large_h}


def for_site(session: Session, business_id: int | None, base: str = "") -> dict:
    if business_id is None:
        return {"shop": [], "items": {}}
    return {"shop": [out(p, base) for p in shop_photos(session, business_id)],
            "items": {k: out(p, base) for k, p in item_photos(session, business_id).items()}}


_FRACTIONS = {"½": " 1/2 ", "¼": " 1/4 ", "¾": " 3/4 "}
_STOP = {"of", "with", "and", "the", "a", "an", "for", "in"}
_UNITS = {"kg", "kgs", "g", "gm", "gms", "gram", "grams", "ml", "l", "litre", "liter", "pc", "pcs", "piece", "pieces"}
MAX_TIED = 3  # "Cake" on a menu of five cakes says nothing: no match rather than a photo on every cake


def _tokens(text: str) -> set[str]:
    t = text.lower()
    for k, v in _FRACTIONS.items():
        t = t.replace(k, v)
    t = re.sub(r"[^a-z0-9/]+", " ", t)
    out = set()
    for w in t.split():
        if w in _STOP:
            continue
        out.add(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)  # cupcakes ~ cupcake
    return out


def _is_size(token: str) -> bool:
    return token in _UNITS or bool(re.fullmatch(r"[0-9/.]+", token))


def match_item(typed: str, names: list[str]) -> list[str]:
    """S17: the item(s) the Reader made from what the seller typed in one row of her list. Most of her words must be in
    the item's name, including at least one real word (not just a size). The best score wins; a tie (she typed no
    size, the Reader made one item per size) gets the photo on each, up to MAX_TIED. No good match: []."""
    want = _tokens(typed)
    if not want or not any(not _is_size(w) for w in want):
        return []
    scored = []
    for name in names:
        have = _tokens(name)
        common = want & have
        if not any(not _is_size(w) for w in common):
            continue
        coverage = len(common) / len(want)
        if coverage < 0.6:
            continue
        scored.append((coverage + 0.1 * len(common) / len(want | have), name))
    if not scored:
        return []
    best = max(s for s, _ in scored)
    tied = [n for s, n in scored if abs(s - best) < 1e-9]
    return tied if len(tied) <= MAX_TIED else []


def remap_items(session: Session, business_id: int, new: list[str]) -> None:
    """S17, after "Read it again": each item photo moves to the new item made from its old name (match_item), or is
    deleted when nothing matches (or that item already has a photo). No commit (the caller saves the profile)."""
    taken = set()
    rows = session.exec(select(Photo).where(Photo.business_id == business_id, Photo.item != "").order_by(Photo.id)).all()
    for p in rows:
        if p.item in new and p.item not in taken:
            taken.add(p.item)
    for p in rows:
        if p.item in new:
            continue
        target = next((n for n in match_item(p.item, new) if n not in taken), None)
        if target is None:
            session.delete(p)
        else:
            p.item = target
            taken.add(target)
            session.add(p)


def follow_items(session: Session, business_id: int, old: list[str], new: list[str]) -> None:
    """After the owner saves her list: a renamed item keeps its photo (same position, new name, and the list kept its
    length, so it was an edit rather than an item added or removed); a photo whose item is gone is deleted.
    No commit (the caller saves the profile in the same transaction)."""
    renamed = {o: n for o, n in zip(old, new, strict=True) if o != n and o not in new} if len(old) == len(new) else {}
    for p in session.exec(select(Photo).where(Photo.business_id == business_id, Photo.item != "")).all():
        if p.item in new:
            continue
        if p.item in renamed and not session.exec(select(Photo.id).where(
                Photo.business_id == business_id, Photo.item == renamed[p.item])).first():
            p.item = renamed[p.item]
            session.add(p)
        else:
            session.delete(p)
