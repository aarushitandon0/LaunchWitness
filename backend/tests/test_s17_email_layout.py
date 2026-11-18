"""S17: every email goes out in one branded layout; the plain text (and a test order's nonce) is untouched."""

import re
from html import escape

from sqlmodel import Session

from app import accounts, outbox
from app.mail import layout
from app.mail.smtp import FakeMailer, SmtpMailer

URL = "https://launchwitness.com/#/signin/confirm?token=abc123XYZ"
SECRETISH = re.compile(r"(?i)(password|api[_-]?key|secret|sk-ant|Bearer )")


def test_sign_in_email_has_both_parts_link_and_brand():
    subject, text, html = accounts.link_email("login", URL)
    assert subject == "Your LaunchWitness sign-in link"  # subjects unchanged
    assert text.startswith("Sign in to LaunchWitness") and URL in text and "launchwitness.com" in text
    assert "You got this because someone entered this address on launchwitness.com." in text
    assert "<h1" in html and "Sign in to LaunchWitness" in html
    assert html.count(URL.replace("&", "&amp;")) >= 2  # the button and the "copy this address" fallback
    assert layout.LOGO_URL in html and 'alt="LaunchWitness"' in html and 'width="32"' in html
    assert f'bgcolor="{layout.BUTTON}"' in html  # Outlook paints the button from bgcolor
    assert not SECRETISH.search(text + html)
    assert "<svg" not in html and "var(--" not in html and "@font-face" not in html and "<style" not in html


def test_delete_email_keeps_its_subject():
    subject, text, html = accounts.link_email("delete", URL)
    assert subject == "Confirm deleting your LaunchWitness account" and URL in text and "Review and delete" in html


def test_button_colours_are_readable():
    assert layout.contrast(layout.BUTTON_TEXT, layout.BUTTON) >= 4.5
    assert layout.contrast(layout.ON_INK, layout.INK) >= 4.5
    assert layout.contrast(layout.MUTED, layout.CARD) >= 4.5


def test_wrap_escapes_and_links_and_keeps_shop_name_as_heading():
    html = layout.wrap("order", "New order for Meera's <Bakes>", "Hi\n\nOpen https://x.example/a?b=1&c=2.\nThanks")
    assert "<h1" in html and "Meera&#x27;s &lt;Bakes&gt;" in html and "<Bakes>" not in html
    assert '<a href="https://x.example/a?b=1&amp;c=2"' in html  # the full stop is not part of the link
    assert layout.WHY["order"] in html


def test_outbox_sends_unchanged_text_and_branded_html(engine, make_settings):
    """The test order's nonce must arrive exactly as written: IMAP matches it in the plain-text part."""
    s = make_settings()
    mailer = FakeMailer()
    body = "Test order from LaunchWitness\nnonce: LW-7f3a9c\nYes, I got it: https://launchwitness.com/#/got-it?token=t1"
    with Session(engine) as session:
        row = outbox.send(session, s, mailer, kind="test_order", key="order:test-1", to="hello@launchwitness.com",
                          subject="[LW test LW-7f3a9c] New order", body=body)
        assert row.status == "sent" and row.priority == outbox.PRIORITY["test_order"]
        again = outbox.send(session, s, mailer, kind="test_order", key="order:test-1", to="hello@launchwitness.com",
                            subject="[LW test LW-7f3a9c] New order", body=body)
        assert again.id == row.id and len(mailer.sent) == 1  # idempotency key unchanged
    sent = mailer.sent[0]
    assert sent["body"] == body and sent["subject"] == "[LW test LW-7f3a9c] New order"
    assert "LW-7f3a9c" in sent["html"] and layout.LOGO_URL in sent["html"] and escape(layout.WHY["test_order"]) in sent["html"]


def test_smtp_message_is_multipart_alternative(monkeypatch, make_settings):
    captured = {}

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            pass

        def send_message(self, msg):
            captured["msg"] = msg

    mailer = SmtpMailer(make_settings(smtp_user="hello@launchwitness.com"))
    monkeypatch.setattr(mailer, "_connect", lambda timeout=0: Conn())
    mailer.send(to="a@example.org", subject="Shop reported", body="plain words here")
    msg = captured["msg"]
    assert msg.get_content_type() == "multipart/alternative"
    assert msg.get_body(("plain",)).get_content().strip() == "plain words here"
    assert layout.LOGO_URL in msg.get_body(("html",)).get_content()
