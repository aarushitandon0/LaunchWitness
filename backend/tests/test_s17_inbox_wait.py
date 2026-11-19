"""S17: the test-order email gets up to 120 s (5 s steps for 30 s, then 10 s), stops at the first find, and the
report says what it's waiting for. The IMAP reader finds new mail by a header scan when the search index lags."""

from email.message import EmailMessage

from sqlmodel import Session, select

from app.agents.checker import INBOX_GAPS, INBOX_WAIT_S
from app.mail import imap, layout
from app.models import CheckRun
from tests.test_m3_launch import approve, meera, plan


def watch_inbox(integ, engine, misses: int | None = None):
    """Wrap the practice inbox: count looks, record sleeps between looks, and what the running CheckRun says."""
    state = {"looks": 0, "naps": [], "waiting_seen": set()}
    real_find = integ.inbox.find

    def find(*, subject_contains, since=None):
        state["looks"] += 1
        with Session(engine) as s:
            run = s.exec(select(CheckRun).where(CheckRun.status == "running")).first()
            if run is not None:
                state["waiting_seen"].add(run.info_json)
        if misses is not None and state["looks"] <= misses:
            return []
        return real_find(subject_contains=subject_contains, since=since)

    def sleep(seconds):
        if state["looks"]:  # only the sleeps between inbox looks
            state["naps"].append(seconds)

    integ.inbox.find, integ.sleep = find, sleep
    return state


def order_check(client, biz):
    rep = client.get(f"/api/businesses/{biz['id']}/report").json()
    return next(c for c in rep["run"]["checks"] if c["check"] == "test_order"), rep


def test_schedule_is_120_seconds():
    assert INBOX_WAIT_S == 120 and sum(INBOX_GAPS) == 120 and INBOX_GAPS[:6] == (5,) * 6 and set(INBOX_GAPS[6:]) == {10}


def test_found_on_the_first_look_passes_at_once(client, engine, integ):
    state = watch_inbox(integ, engine)
    biz = meera(client)
    approve(client, plan(client, biz))
    check, _ = order_check(client, biz)
    assert check["passed"] and state["looks"] == 1 and state["naps"] == []


def test_found_late_stops_at_the_first_find(client, engine, integ):
    state = watch_inbox(integ, engine, misses=8)  # found on the 9th look: 30 s of 5 s steps, then two 10 s steps
    biz = meera(client)
    approve(client, plan(client, biz))
    check, _ = order_check(client, biz)
    assert check["passed"] and state["looks"] == 9 and state["naps"] == [5] * 6 + [10, 10]
    assert any('"waiting_for": "test_email"' in info for info in state["waiting_seen"])  # the report could say so
    with Session(engine) as s:
        assert all("waiting_for" not in r.info_json for r in s.exec(select(CheckRun)).all())  # cleared afterwards


def test_not_found_after_the_full_120_seconds(client, engine, integ):
    state = watch_inbox(integ, engine)
    integ.mailer.drop = True  # accepted by the mail server, never arrives
    biz = meera(client)
    approve(client, plan(client, biz))
    check, rep = order_check(client, biz)
    assert check["passed"] is False and "hasn't arrived" in check["plain"] and "after 120 s" in check["detail"]
    assert state["naps"] == list(INBOX_GAPS) and state["looks"] == len(INBOX_GAPS) + 1
    assert rep["run"]["status"] == "done" and "waiting_for" not in rep["run"]["info"]


# ---------- the IMAP reader: search OR a scan of the newest subjects ----------

def _raw(subject: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, "hello@launchwitness.com", "hello@launchwitness.com"
    msg.set_content(body)
    msg.add_alternative(layout.wrap("test_order", subject, body), subtype="html")
    return msg.as_bytes()


class FakeImap:
    """INBOX with numbered messages; `search_works=False` is a lagging search index (finds nothing)."""

    def __init__(self, messages: list[bytes], search_works: bool):
        self.messages, self.search_works, self.fetched = messages, search_works, []

    def __call__(self, *a, **k):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a):
        pass

    def select(self, box, readonly=False):
        assert readonly  # never marks anything as read
        return "OK", [str(len(self.messages)).encode()]

    def search(self, _charset, *criteria):
        if not self.search_works:
            return "OK", [b""]
        text = criteria[1].strip('"')
        return "OK", [b" ".join(str(i + 1).encode() for i, m in enumerate(self.messages) if text.encode() in m)]

    def fetch(self, which, what):
        self.fetched.append((which, what))
        date = b'INTERNALDATE "19-Nov-2026 01:31:55 +0530"'
        if b":" in (which if isinstance(which, bytes) else str(which).encode()):
            first, last = (int(x) for x in which.split(b":"))
            out = []
            for n in range(first, last + 1):
                head = self.messages[n - 1].split(b"\n\n", 1)[0] + b"\n\n"
                subj, inside = [], False
                for line in head.split(b"\n"):  # the Subject line plus its folded continuation lines, as servers send
                    inside = line.lower().startswith(b"subject") or (inside and line[:1] in (b" ", b"\t"))
                    if inside:
                        subj.append(line)
                subj = b"\n".join(subj)
                out += [(b"%d (BODY[HEADER.FIELDS (SUBJECT)] {%d}" % (n, len(subj)), subj + b"\r\n\r\n"), b")"]
            return "OK", out
        raw = self.messages[int(which) - 1]
        return "OK", [(b"%s (%s RFC822 {%d}" % (which, date, len(raw)), raw), b")"]


def _reader(monkeypatch, make_settings, fake):
    monkeypatch.setattr(imap.imaplib, "IMAP4_SSL", fake)
    return imap.ImapInboxReader(make_settings(imap_user="hello@launchwitness.com"))


def test_header_scan_finds_mail_the_search_misses(monkeypatch, make_settings):
    old = [_raw(f"Other mail {i}", "hello") for i in range(25)]
    new = _raw("TEST, not a real order: Meera's Eggless Bakes (LW-1) [2523c0b518ae6a89]",
               "Test order\ncode 2523c0b518ae6a89\n")
    fake = FakeImap(old + [new], search_works=False)
    found = _reader(monkeypatch, make_settings, fake).find(subject_contains="2523c0b518ae6a89")
    assert len(found) == 1 and "code 2523c0b518ae6a89" in found[0].body
    assert (b"7:26", "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])") in fake.fetched  # only the newest 20, PEEK: not marked read


def test_search_and_scan_together_never_return_a_message_twice(monkeypatch, make_settings):
    new = _raw("TEST, not a real order: Shop (LW-2) [aaaabbbbccccdddd]", "code aaaabbbbccccdddd")
    found = _reader(monkeypatch, make_settings, FakeImap([new], search_works=True)).find(subject_contains="aaaabbbbccccdddd")
    assert len(found) == 1


def test_nothing_found_when_neither_way_finds_it(monkeypatch, make_settings):
    fake = FakeImap([_raw("Something else", "x")], search_works=False)
    assert _reader(monkeypatch, make_settings, fake).find(subject_contains="2523c0b518ae6a89") == []


def test_empty_inbox(monkeypatch, make_settings):
    assert _reader(monkeypatch, make_settings, FakeImap([], search_works=False)).find(subject_contains="x") == []
