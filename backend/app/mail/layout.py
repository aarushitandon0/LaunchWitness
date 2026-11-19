"""One branded layout for every email LaunchWitness sends (S17).

Email-safe: tables, inline styles, bgcolor for Outlook, no CSS variables, no SVG, no web fonts, 560 px wide.
The plain-text part is never changed by the layout's HTML: whatever text a sender wrote (including a test
order's nonce) goes out exactly as written, and the HTML shows the same words.

Two ways in:
- `render(...)`: an email that knows its heading and button (sign-in, delete account).
- `wrap(kind, subject, body)`: any other plain-text email (orders, alerts, team notes); used by the outbox and the
  mailer when a sender gives no HTML. Addresses in the text become links.
"""

from __future__ import annotations

import re
from html import escape

LOGO_URL = "https://launchwitness.com/logo-mark-128.png"
SITE = "launchwitness.com"

INK = "#161614"  # header band: the app's dark frame
ON_INK = "#f3eee4"
TEXT = "#1b1b19"
MUTED = "#6b665c"
PAGE = "#f5efe4"  # the app's cream
CARD = "#ffffff"
BUTTON = "#dcf06a"  # brand lime (the logo's lime, the app's accent)
BUTTON_TEXT = "#1d2205"  # 13.0:1 on the lime (WCAG AA needs 4.5:1; tested)
FONT = "Arial,Helvetica,sans-serif"

WHY = {
    "login": "You got this because someone entered this address on launchwitness.com.",
    "delete": "You got this because someone asked to delete the LaunchWitness account for this address.",
    "order": "You got this because your shop on LaunchWitness sends its orders to this address.",
    "test_order": "You got this because LaunchWitness checks that your shop's orders reach this address. It was a check, not an order.",
    "alert": "You got this because LaunchWitness keeps checking your shop and tells you when something needs you.",
    "watch": "You got this because you asked LaunchWitness to watch this address every day.",
    "team": "You got this because you run or use LaunchWitness.",
    "contact": "You got this because someone used the contact form on launchwitness.com.",
}
DEFAULT_WHY = "You got this because of a shop or account on launchwitness.com."

URL = re.compile(r"https?://[^\s<>\"']+")


def contrast(fg: str, bg: str) -> float:
    def lum(hex_: str) -> float:
        rgb = [int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _linkify(text: str) -> str:
    out, last = [], 0
    for m in URL.finditer(text):
        url = m.group(0).rstrip(".,);")
        out.append(escape(text[last:m.start()]))
        out.append(f'<a href="{escape(url, quote=True)}" style="color:{TEXT};text-decoration:underline">{escape(url)}</a>')
        last = m.start() + len(url)
    out.append(escape(text[last:]))
    return "".join(out)


def _paragraphs(text: str) -> str:
    blocks = [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    return "".join(f'<p style="margin:0 0 14px 0">{_linkify(b).replace(chr(10), "<br>")}</p>' for b in blocks)


def _button(label: str, url: str) -> str:
    href = escape(url, quote=True)
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:6px 0 18px 0"><tr>'
            f'<td bgcolor="{BUTTON}" style="border-radius:10px;background:{BUTTON}">'
            f'<a href="{href}" style="display:inline-block;padding:13px 22px;font-family:{FONT};font-size:16px;'
            f'font-weight:bold;color:{BUTTON_TEXT};text-decoration:none;border-radius:10px">{escape(label)}</a>'
            f"</td></tr></table>")


def _page(heading: str, inner: str, why: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(heading) + "</title></head>"
        f'<body style="margin:0;padding:0;background:{PAGE}">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{PAGE}" style="background:{PAGE}">'
        '<tr><td align="center" style="padding:24px 12px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;width:100%">'
        # header band
        f'<tr><td bgcolor="{INK}" style="background:{INK};border-radius:14px 14px 0 0;padding:16px 22px">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td style="vertical-align:middle;padding-right:10px"><img src="{LOGO_URL}" width="32" height="32" alt="LaunchWitness" '
        'style="display:block;border:0;width:32px;height:32px"></td>'
        f'<td style="vertical-align:middle;font-family:{FONT};font-size:18px;font-weight:bold;color:{ON_INK}">LaunchWitness</td>'
        "</tr></table></td></tr>"
        # body card
        f'<tr><td bgcolor="{CARD}" style="background:{CARD};border-radius:0 0 14px 14px;padding:24px 22px 10px 22px;'
        f'font-family:{FONT};font-size:16px;line-height:1.5;color:{TEXT}">'
        f'<h1 style="margin:0 0 14px 0;font-family:{FONT};font-size:21px;line-height:1.3;color:{TEXT}">{escape(heading)}</h1>'
        + inner + "</td></tr>"
        # footer
        f'<tr><td style="padding:16px 22px;font-family:{FONT};font-size:13px;line-height:1.5;color:{MUTED}">'
        f'LaunchWitness, <a href="https://{SITE}" style="color:{MUTED}">{SITE}</a><br>{escape(why)}</td></tr>'
        "</table></td></tr></table></body></html>"
    )


def render(*, heading: str, lead: str, button: tuple[str, str] | None, after: str = "", why: str,
           fallback_url: str | None = None) -> tuple[str, str]:
    """(plain text, HTML) for an email with a heading and one button. Same words in both."""
    url = fallback_url or (button[1] if button else None)
    text_parts = [heading, lead]
    if url:
        text_parts.append(url)
    if after:
        text_parts.append(after)
    text_parts.append(f"- LaunchWitness, {SITE}\n{why}")
    text = "\n\n".join(text_parts)

    inner = _paragraphs(lead)
    if button:
        inner += _button(*button)
    if after:
        inner += _paragraphs(after)
    if url:
        inner += (f'<p style="margin:0 0 14px 0;font-size:13px;color:{MUTED}">If the button doesn\'t work, copy this '
                  f'address into your browser:<br><a href="{escape(url, quote=True)}" style="color:{MUTED};'
                  f'word-break:break-all">{escape(url)}</a></p>')
    return text, _page(heading, inner, why)


TEST_BG = "#ecebe7"  # S19B: the neutral grey banner of a test email (never the order styling)
TEST_EDGE = "#8a857b"


def _test_banner(text: str) -> str:
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 16px 0">'
            f'<tr><td bgcolor="{TEST_BG}" style="background:{TEST_BG};border-left:4px solid {TEST_EDGE};border-radius:8px;'
            f'padding:12px 14px;font-family:{FONT};font-size:15px;line-height:1.45;color:{TEXT}" data-lw="test-banner">'
            f"{_linkify(text)}</td></tr></table>")


def wrap(kind: str | None, subject: str, body: str) -> str:
    """HTML for a plain-text email: the same words, in the branded layout. The subject is the heading, so a
    seller's order email keeps the shop's name as its subject; LaunchWitness appears only in the header band.
    A test order's first paragraph (its "this is a check" line) is shown as a grey banner instead (S19B)."""
    inner = _paragraphs(body)
    if kind == "test_order":
        first, _sep, rest = body.strip().partition("\n\n")
        inner = _test_banner(" ".join(first.split())) + _paragraphs(rest)
    return _page(subject, inner, WHY.get(kind or "", DEFAULT_WHY))
