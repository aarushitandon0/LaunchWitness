"""What ANY website address does when a visitor types it, in plain words (S11b).

Two halves, so every case can be tested from a saved observation:
- `observe()` looks (read-only: public DNS, one secure request to the home page, one secure handshake, one plain
  http request with no body) and returns a `Seen`;
- `judge()` turns a `Seen` into findings. It only says what we saw: a status code alone never becomes "your site
  works", and something that failed on OUR side becomes "couldn't check", never a fault of theirs.

Findings have the same shape as in `mail_setup.py` (check, ok, plain, detail, sure, code, steps, action).
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.checks.dns_resolver import DnsResolver, lookup
from app.checks.mail_setup import COULDNT, NOT_SEEN, OUR_SIDE, SEEN, finding
from app.checks.safe_fetch import NotHttps, PrivateAddress, Refused, TooManyRedirects

SLOW_SECONDS = 5.0
CERT_WARN_DAYS = 14
HOST_STEPS = "Whoever hosts this website can fix this: show them this result."


@dataclass
class Seen:
    host: str
    dns: str = ""  # ok | nodata (name exists, no website address) | nxdomain | error (our lookup failed)
    ips: tuple[str, ...] = ()
    fetch: str = ""  # "" not tried | ok | timeout | refused | cert | loop | private | to_http | blocked | error
    status: int | None = None
    seconds: float = 0.0
    hsts: bool = False
    final_host: str = ""
    tls: str = ""  # "" not looked | ok | expired | not_yet_valid | wrong_host | self_signed | untrusted | bad_cert | ...
    cert_days: int | None = None
    http: str = ""  # "" not looked | redirects_https | redirects_http | serves | error | closed | timeout
    http_to: str = ""
    note: str = ""


def readable(host: str) -> str:
    """An internationalised name the way people write it (xn--mnchen-3ya.de -> münchen.de)."""
    if "xn--" not in host:
        return host
    try:
        return host.encode("ascii").decode("idna")
    except UnicodeError:
        return host


def observe(host: str, dns: DnsResolver, web, light: bool = False) -> Seen:
    from urllib.parse import urlsplit

    s = Seen(host)
    a, aaaa = lookup(dns, host, "A"), lookup(dns, host, "AAAA")
    s.ips = tuple(a.values + aaaa.values)
    s.dns = ("ok" if s.ips else "error" if "error" in (a.status, aaaa.status) else
             "nxdomain" if a.status == "nxdomain" else "nodata")
    if not s.ips:
        return s
    try:
        page = web.get(f"https://{host}/")
        s.status, s.seconds, s.hsts = page.status, round(getattr(page, "seconds", 0.0), 1), getattr(page, "hsts", False)
        s.final_host = urlsplit(page.url).hostname or host
        s.note = page.error
        s.fetch = "ok" if page.status is not None else (
            getattr(page, "kind", "") or ("cert" if not page.cert_valid else
                                          "timeout" if "imeout" in page.error or page.error == "TooSlow" else "error"))
    except TooManyRedirects:
        s.fetch = "loop"
    except PrivateAddress as e:
        s.fetch, s.note = "private", str(e)
    except NotHttps as e:
        s.fetch, s.note = "to_http", str(e)
    except Refused as e:
        s.fetch, s.note = "blocked", str(e)
    if light or s.fetch == "private":
        return s
    try:
        look = getattr(web, "tls_look", None)
        if look is not None and s.fetch != "timeout":
            t = look(host)
            s.tls, s.note = t.kind, (t.detail or s.note)
            s.cert_days = (t.not_after - datetime.now(UTC)).days if t.not_after else None
        elif look is None and s.fetch == "ok":  # an older fetcher: only the end date of a working certificate
            end = web.cert_not_after(host)
            s.tls, s.cert_days = "ok", (end - datetime.now(UTC)).days if end else None
        first = getattr(web, "http_first", None)
        if first is not None:
            s.http, s.http_to = first(host)
    except Refused as e:
        s.note = str(e)
    return s


CERT_TEXT = {
    "expired": "The security certificate has expired, so browsers show a warning instead of the site.",
    "not_yet_valid": "The security certificate isn't valid yet (its start date is in the future), so browsers show a "
                     "warning instead of the site.",
    "wrong_host": "The security certificate belongs to a different name, so browsers show a warning instead of the site.",
    "self_signed": "The security certificate was made by the site itself, not by a trusted authority, so browsers "
                   "show a warning instead of the site.",
    "untrusted": "The security certificate comes from an authority browsers don't trust, so browsers show a warning "
                 "instead of the site.",
    "bad_cert": "The security certificate didn't pass our check, so browsers are likely to show a warning instead of "
                "the site.",
}
CERT_STEPS = "Whoever hosts this website needs to install a valid certificate for exactly this name: show them this result."


def judge(s: Seen, twin: Seen | None = None) -> list[dict]:
    name, out = readable(s.host), []
    if s.dns == "error":
        return [finding("address", None, OUR_SIDE, f"A/AAAA {s.host}: lookup failed", COULDNT, "addr_couldnt_check")]
    if s.dns == "nxdomain":
        return [finding("address", False, "The address doesn't lead anywhere: this name isn't set up on the internet.",
                        f"A/AAAA {s.host}: no such name", NOT_SEEN, "addr_nxdomain",
                        "Check the spelling. If it's your name, add its website address where your domain is managed.")]
    if s.dns == "nodata":
        return [finding("address", False, "The name exists, but it doesn't lead to a website server.",
                        f"A/AAAA {s.host}: no records", NOT_SEEN, "addr_nodata",
                        "Where your domain is managed, add the website address your host gave you for this name.")]
    out.append(finding("address", True, "The address leads to a website server.", ", ".join(s.ips), SEEN, "addr_ok"))
    detail = f"https://{s.host}/ -> status {s.status} {s.note}".strip()
    # a page that opened has a certificate the fetch accepted: a second look that disagrees is our doubt, not a fault
    cert_kind = "" if s.fetch == "ok" else s.tls if s.tls in CERT_TEXT else ("bad_cert" if s.fetch == "cert" else "")
    if cert_kind:
        out.append(finding("https", False, CERT_TEXT[cert_kind], f"{detail}; certificate: {cert_kind}", SEEN,
                           f"cert_{cert_kind}", CERT_STEPS))
    elif s.fetch == "timeout":
        out.append(finding("https", False, "The name leads to a server, but nothing answered in time.", detail, SEEN,
                           "web_timeout", HOST_STEPS))
    elif s.fetch in ("refused", "error") and s.http == "serves":
        out.append(finding("https", False, "This site answers only on plain http, with no padlock: browsers warn "
                           "visitors that it is not secure.", f"{detail}; http://{s.host}/ -> {s.http_to}", SEEN,
                           "web_http_only", "Ask whoever hosts this website to switch on https (a free certificate "
                           "is enough) and to send http visitors to it."))
    elif s.fetch == "refused":
        out.append(finding("https", False, "The name leads to a server, but it didn't accept a secure connection.",
                           detail, SEEN, "web_refused", HOST_STEPS))
    elif s.fetch == "loop":
        out.append(finding("https", False, "The address keeps sending visitors on to another page without ever "
                           "arriving (too many redirects).", detail, SEEN, "web_redirect_loop", HOST_STEPS))
    elif s.fetch == "to_http":
        out.append(finding("https", False, "The secure address sends visitors back to plain http, with no padlock: "
                           "browsers warn visitors that it is not secure.", f"{detail}; http://{s.host}/ -> {s.http} "
                           f"{s.http_to}", SEEN, "web_https_to_http", "Ask whoever hosts this website to keep "
                           "visitors on https instead of sending them back to http."))
    elif s.fetch == "private":
        out.append(finding("https", None, s.note, detail, COULDNT, "web_private"))
    elif s.fetch == "blocked":
        out.append(finding("https", None, "The address sends visitors on to a page we don't open (not secure, or "
                           "not public), so we stopped there.", f"{detail}; {s.note}", COULDNT, "web_blocked"))
    elif s.fetch != "ok":
        out.append(finding("https", None, "We reached the server, but the answer broke off before we could read it.",
                           detail, COULDNT, "web_error"))
    else:
        out.append(_status(s, name, detail))
    if s.fetch == "ok" and s.seconds > SLOW_SECONDS:
        out.append(finding("speed", None, f"It answered, but slowly (about {round(s.seconds)} seconds). Visitors may "
                           "give up waiting.", f"{s.seconds}s", SEEN, "web_slow", HOST_STEPS))
    if s.cert_days is not None and s.fetch == "ok" and s.tls == "ok":  # only next to a page that really opened
        ok = s.cert_days >= CERT_WARN_DAYS
        out.append(finding("certificate", ok, f"The security certificate is good for {s.cert_days} more days." if ok
                           else f"The security certificate runs out in {s.cert_days} days.", f"{s.cert_days} days left",
                           SEEN, "cert_days_ok" if ok else "cert_expiring", "" if ok else
                           "Certificates normally renew themselves. Ask whoever hosts this website why this one hasn't."))
    if s.http == "redirects_https":
        out.append(finding("plain_http", True, "Visitors who type the address without https are sent to the secure "
                           "site.", f"http://{s.host}/ -> https://{s.http_to}", SEEN, "http_redirects"))
    elif s.http in ("serves", "redirects_http") and s.fetch == "ok":
        out.append(finding("plain_http", None, "The site also answers on plain http without sending visitors to the "
                           "secure version.", f"http://{s.host}/ -> {s.http} {s.http_to}", SEEN, "http_no_redirect",
                           "Ask whoever hosts this website to send http visitors to https."))
    if s.hsts:
        out.append(finding("hsts", True, "It tells browsers to always use the secure version (extra protection).",
                           "Strict-Transport-Security present", SEEN, "hsts_present"))
    if twin is not None:
        out.extend(_twin(s, twin))
    return out


def _status(s: Seen, name: str, detail: str) -> dict:
    moved = f" (after sending us on to {readable(s.final_host)})" if s.final_host and s.final_host != s.host else ""
    code = s.status or 0
    if code in (401, 403, 429):
        return finding("https", None, f"The site answered securely but turned our check away (code {code}){moved}. "
                       "It may still open for ordinary visitors.", detail, COULDNT, "web_turned_away")
    if code >= 500:
        return finding("https", False, f"The site answered securely, but with an error on its side (code {code}){moved}.",
                       detail, SEEN, "web_server_error", HOST_STEPS)
    if code >= 400:
        return finding("https", False, "The site answered securely, but its home page wasn't there "
                       f"(code {code}){moved}.", detail, SEEN, "web_client_error", HOST_STEPS)
    return finding("https", True, f"The home page answered over a secure connection (code {code}){moved}.", detail,
                   SEEN, "web_ok")


def works(s: Seen) -> bool:
    return s.fetch == "ok" and s.status is not None and s.status < 400


def _twin(s: Seen, twin: Seen) -> list[dict]:
    """The same site with and without www: say so when one opens and the other doesn't."""
    if twin.dns == "error" or twin.fetch in ("private", "blocked") or works(s) == works(twin):
        return []
    good, bad = (s, twin) if works(s) else (twin, s)
    detail = f"{good.host}: status {good.status}; {bad.host}: dns {bad.dns}, {bad.fetch or 'not tried'} {bad.status or ''}"
    if bad.dns in ("nxdomain", "nodata"):
        return [finding("www", None, f"{readable(good.host)} opens, but {readable(bad.host)} isn't set up, so visitors "
                        "who type that one won't arrive.", detail, NOT_SEEN, "www_not_set_up",
                        f"Where your domain is managed, point {readable(bad.host)} to the same place as "
                        f"{readable(good.host)}.")]
    return [finding("www", False, f"{readable(good.host)} opens, but {readable(bad.host)} doesn't, so visitors who "
                    "type that one won't arrive.", detail, SEEN, "www_disagree", HOST_STEPS)]


def twin_of(host: str, dns: DnsResolver) -> str | None:
    """The other spelling to compare: the bare name for www.x; www.x for a name that is a domain of its own."""
    if host.startswith("www."):
        return host[4:]
    return f"www.{host}" if lookup(dns, host, "NS").values else None


def web_findings(host: str, dns: DnsResolver, web) -> list[dict]:
    seen = observe(host, dns, web)
    other = twin_of(host, dns) if seen.dns == "ok" else None
    return judge(seen, observe(other, dns, web, light=True) if other else None)
