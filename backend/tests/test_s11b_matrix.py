"""S11b offline matrix: every website and email case → the exact plain words, how sure we are, and whose steps.

Nothing here touches the network. `docs/CHECKS_MATRIX.md` lists each row next to the test that proves it.
The words are written out here on purpose (not imported), so a wording change has to be made twice.
"""

import ssl

import httpx
import pytest

from app.checks import mail_setup as ms
from app.checks import web_setup as ws
from app.checks.dns_resolver import FakeDnsResolver, txt_value
from app.checks.safe_fetch import PrivateAddress, Refused, SafeWeb, TlsSeen, TooManyRedirects, tls_kind

D = "shop.example"  # the domain every mail case is about

# provider -> its healthy setup: mail servers, the name its SPF line refers to, its signing label
SETUPS = {
    "google": (["1 smtp.google.com."], "_spf.google.com", "~all", "google"),
    "microsoft": (["0 shop-example.mail.protection.outlook.com."], "spf.protection.outlook.com", "-all", "selector1"),
    "zoho": (["10 mx.zoho.com.", "20 mx2.zoho.com.", "50 mx3.zoho.com."], "zohomail.com", "~all", "zmail"),
    "zoho_in": (["10 mx.zoho.in.", "20 mx2.zoho.in.", "50 mx3.zoho.in."], "zoho.in", "~all", "zmail"),
    "secureserver": (["0 smtp.secureserver.net.", "10 mailstore1.secureserver.net."], "secureserver.net", "-all", ""),
    "titan": (["10 mx1.titan.email.", "20 mx2.titan.email."], "spf.titan.email", "~all", "titan1"),
    "hostinger": (["5 mx1.hostinger.com.", "10 mx2.hostinger.com."], "_spf.mail.hostinger.com", "~all", "hostingermail-a"),
    "cloudflare": (["10 route1.mx.cloudflare.net.", "20 route2.mx.cloudflare.net."], "_spf.mx.cloudflare.net", "~all",
                   "cf2024-1"),
}
LABELS = {"google": "Google Workspace (Gmail)", "microsoft": "Microsoft 365 (Outlook)", "zoho": "Zoho Mail",
          "zoho_in": "Zoho Mail (India)", "secureserver": "GoDaddy Professional Email", "titan": "Titan Email",
          "hostinger": "Hostinger Email", "cloudflare": "Cloudflare Email Routing"}
OUR_SIDE = "We couldn't read this just now (the problem was on our side, not theirs). Please try again in a few minutes."


def zone(provider: str | None = "google", **change) -> FakeDnsResolver:
    """A healthy domain on `provider`; `change` replaces records: key "TYPE name" → values (None removes)."""
    rec: dict[tuple[str, str], list[str]] = {(D, "A"): ["93.184.216.34"]}
    if provider:
        mx, inc, all_, sel = SETUPS[provider]
        rec[(D, "MX")] = mx
        for m in mx:
            rec[(m.split()[1].rstrip("."), "A")] = ["93.184.216.40"]
        rec[(D, "TXT")] = [f'"v=spf1 include:{inc} {all_}"']
        rec[(inc, "TXT")] = ['"v=spf1 ip4:192.0.2.0/24 -all"']
        if sel:
            rec[(f"{sel}._domainkey.{D}", "TXT")] = ['"v=DKIM1; k=rsa; p=MIIBIjANBgkq"']
        rec[(f"_dmarc.{D}", "TXT")] = ['"v=DMARC1; p=quarantine"']
    for key, values in change.items():
        rtype, name = key.split("__")
        k = (name.replace("_AT_", D).replace("__", "."), rtype)
        if values is None:
            rec.pop(k, None)
        else:
            rec[k] = values
    return FakeDnsResolver(rec)


def found(dns, host=D) -> dict[str, dict]:
    return {f["check"]: f for f in ms.mail_findings(host, dns)}


def other_values(provider: str) -> list[str]:
    """Every OTHER service's own settings: none of these may ever appear in advice for `provider`."""
    out = []
    for key, (mx, inc, _all, _sel) in SETUPS.items():
        if key.split("_")[0] != provider.split("_")[0]:
            out += [inc] + [m.split()[1].rstrip(".") for m in mx]
    return [v for v in out if not (provider == "microsoft" and v == "secureserver.net")]  # GoDaddy-sold Microsoft 365


# ---------- every provider: detection, healthy, and each problem with only ITS OWN steps ----------

@pytest.mark.parametrize("provider", sorted(SETUPS))
def test_provider_is_detected_and_a_healthy_setup_is_all_good(provider):
    f = found(zone(provider))
    assert f["email_mx"]["provider"] == provider
    assert (f["email_mx"]["ok"], f["email_mx"]["sure"]) == (True, "seen")
    assert f["email_mx"]["plain"] == f"Emails to this address have somewhere to go: {LABELS[provider]}."
    assert f["email_spf"]["ok"] is True and f["email_spf"]["code"] in ("spf_ok_soft", "spf_ok_hard")
    assert f["email_dmarc"]["plain"] == "It is protected against fake emails in its name: they are sent to spam."
    if SETUPS[provider][3]:
        assert (f["email_dkim"]["ok"], f["email_dkim"]["sure"]) == (True, "seen")
        assert f["email_dkim"]["plain"] == "Its emails can be signed: we found a signing key."
    assert all(x["steps"] == "" and x["action"] == "none" for x in f.values() if x["ok"])


PROBLEMS = {  # name: (records to change, check, code, ok, sure, exact plain words)
    "spf_missing": ({"TXT___AT_": None}, "email_spf", "spf_missing", False, "not_seen",
                    "It doesn't say which servers may send its email, so its emails may land in spam."),
    "spf_two_lines": ({"TXT___AT_": ['"v=spf1 include:a.example -all"', '"v=spf1 include:b.example -all"']},
                      "email_spf", "spf_multiple", False, "seen",
                      "It has more than one sending-permission line. Mail services treat that as an error, so "
                      "neither line counts and its emails may land in spam."),
    "spf_plus_all": ({"TXT___AT_": ['"v=spf1 ip4:192.0.2.1 +all"']}, "email_spf", "spf_plus_all", False, "seen",
                     "Its sending-permission line allows every server in the world to send as this address, so it "
                     "protects nothing."),
    "spf_neutral_all": ({"TXT___AT_": ['"v=spf1 ip4:192.0.2.1 ?all"']}, "email_spf", "spf_neutral_all", False, "seen",
                        "Its sending-permission line takes no position on other servers, so it protects nothing."),
    "spf_syntax": ({"TXT___AT_": ['"v=spf1 inlcude:x.example -all"']}, "email_spf", "spf_syntax", False, "seen",
                   "Its sending-permission line has a mistake in it, so mail services can't read it."),
    "dmarc_missing": ({"TXT___dmarc._AT_": None}, "email_dmarc", "dmarc_missing", False, "not_seen",
                      "It isn't protected against fake emails in its name."),
    "dmarc_two_lines": ({"TXT___dmarc._AT_": ['"v=DMARC1; p=none"', '"v=DMARC1; p=reject"']}, "email_dmarc",
                        "dmarc_multiple", False, "seen",
                        "It has more than one fake-email protection line, so mail services ignore them all."),
    "dmarc_syntax": ({"TXT___dmarc._AT_": ['"v=DMARC1; p=block"']}, "email_dmarc", "dmarc_syntax", False, "seen",
                     "Its fake-email protection line has a mistake in it, so mail services ignore it."),
    "dmarc_none": ({"TXT___dmarc._AT_": ['"v=DMARC1; p=none"']}, "email_dmarc", "dmarc_none", None, "seen",
                   "It only watches for fake emails in its name (monitoring only): fake mail in its name still gets "
                   "through."),
}


@pytest.mark.parametrize("provider", sorted(SETUPS))
@pytest.mark.parametrize("problem", sorted(PROBLEMS))
def test_each_problem_on_each_provider(provider, problem):
    change, check, code, ok, sure, plain = PROBLEMS[problem]
    f = found(zone(provider, **change))[check]
    assert (f["code"], f["ok"], f["sure"], f["plain"]) == (code, ok, sure, plain)
    assert f["action"] == "explain" and f["steps"]  # we explain; nothing is offered or applied
    assert not [v for v in other_values(provider) if v in f["steps"]], "advice names another service's settings"
    assert D not in f["plain"] and "v=" not in f["plain"]  # names and values stay in the technical details


@pytest.mark.parametrize("provider", sorted(SETUPS))
def test_spf_that_does_not_name_the_detected_provider_is_a_note_not_a_verdict(provider):
    f = found(zone(provider, TXT___AT_=['"v=spf1 include:other.example -all"'],
                   **{"TXT__other.example": ['"v=spf1 ip4:192.0.2.9 -all"']}))["email_spf"]
    label = LABELS[provider]
    assert (f["code"], f["ok"], f["sure"]) == ("spf_not_covering", None, "not_seen")
    assert f["plain"] == (f"It has a sending-permission line, but we didn't see {label} named in it. If this address "
                          f"sends email through {label}, those emails may land in spam.")
    assert SETUPS[provider][1] in f["steps"] or provider.startswith("zoho")
    assert not [v for v in other_values(provider) if v in f["steps"]]


@pytest.mark.parametrize("provider", sorted(SETUPS))
def test_dkim_is_never_called_missing(provider):
    """No key under the labels we know → "couldn't check", because the owner may use a label we can't guess."""
    sel = SETUPS[provider][3]
    f = found(zone(provider, **({f"TXT__{sel}._domainkey._AT_": None} if sel else {})))["email_dkim"]
    assert (f["ok"], f["sure"], f["code"]) == (None, "couldnt_check", "dkim_couldnt_check")
    assert f["plain"] == ("We couldn't check whether its emails are signed: a signing key can only be looked up by its "
                          "private label, and we don't know this address's.")
    assert "missing" not in f["plain"] and "aren't signed" not in f["plain"]
    assert not [v for v in other_values(provider) if v in f["steps"]]


@pytest.mark.parametrize("provider", sorted(SETUPS))
def test_mail_servers_that_do_not_exist(provider):
    gone = {f"A__{m.split()[1].rstrip('.')}": None for m in SETUPS[provider][0]}
    f = found(zone(provider, **gone))["email_mx"]
    assert (f["code"], f["ok"], f["sure"]) == ("mx_unresolvable", False, "seen")
    assert f["plain"] == "Its mail servers are listed by names that don't exist, so emails to it can't be delivered."
    assert LABELS[provider] in f["steps"] and not [v for v in other_values(provider) if v in f["steps"]]


# ---------- cases that don't depend on the provider ----------

def test_zoho_own_spf_names_count_as_zoho():  # found on the real zoho.com: include:spf.zoho.com, spf.zohomail.com
    f = found(zone("zoho", TXT___AT_=['"v=spf1 include:spf.zoho.com -all"'],
                   **{"TXT__spf.zoho.com": ['"v=spf1 ip4:192.0.2.0/24 -all"']}))["email_spf"]
    assert f["code"] == "spf_ok_hard"


def test_microsoft_365_from_godaddy_uses_the_godaddy_spf_name():
    f = found(zone("microsoft", TXT___AT_=['"v=spf1 include:secureserver.net -all"'],
                   **{"TXT__secureserver.net": ['"v=spf1 ip4:192.0.2.0/24 -all"']}))["email_spf"]
    assert f["code"] == "spf_ok_hard"


def test_null_mx_no_mx_unknown_and_mixed():
    f = found(zone(None, MX___AT_=["0 ."]))
    assert (f["email_mx"]["code"], f["email_mx"]["ok"], f["email_mx"]["sure"]) == ("mx_null", False, "seen")
    assert f["email_mx"]["plain"] == "This address says it doesn't accept email."
    assert f["email_dkim"]["code"] == "dkim_not_applicable" and f["email_dkim"]["ok"] is None
    f = found(zone(None))
    assert (f["email_mx"]["code"], f["email_mx"]["ok"], f["email_mx"]["sure"]) == ("mx_none", False, "not_seen")
    assert f["email_mx"]["plain"] == ("This address has no mail servers listed, so emails sent to it will almost "
                                      "certainly not arrive.")
    unknown = zone(None, MX___AT_=["10 in1.mailhost.example."], **{"A__in1.mailhost.example": ["93.184.216.41"]})
    f = found(unknown)
    assert (f["email_mx"]["provider"], f["email_mx"]["ok"]) == ("unknown", True)
    assert f["email_mx"]["plain"] == "Emails to this address have somewhere to go (an email service we don't recognise)."
    for check in ("email_spf", "email_dkim"):  # unknown service: we say so and give NO values
        assert f[check]["steps"] == ms.UNKNOWN_STEPS and "include:" not in f[check]["steps"]
    assert f["email_dkim"]["detail"] == "no known label to try"  # no guessing at labels either
    mixed = zone("google", MX___AT_=["1 smtp.google.com.", "10 mx1.titan.email."],
                 **{"A__mx1.titan.email": ["93.184.216.42"]})
    f = found(mixed)["email_mx"]
    assert (f["code"], f["ok"]) == ("mx_mixed", None)
    assert f["plain"] == ("Emails to this address are split between two different email services (Google Workspace "
                          "(Gmail) and Titan Email), so some may go to the wrong one.")


def test_mx_alias_ip_literal_and_one_dead_server():
    f = found(zone("google", **{"CNAME__smtp.google.com": ["elsewhere.example."]}))["email_mx"]
    assert (f["code"], f["ok"], f["sure"]) == ("mx_cname", None, "seen")
    assert f["plain"] == ("Its mail server name is an alias for another name. The rules for email don't allow that, "
                          "and some mail services refuse it.")
    f = found(zone(None, MX___AT_=["10 93.184.216.34."]))["email_mx"]
    assert (f["code"], f["ok"]) == ("mx_ip_literal", False)
    assert f["plain"] == "Its mail server is listed as a bare number instead of a name, which mail services refuse."
    f = found(zone("titan", **{"A__mx2.titan.email": None}))["email_mx"]
    assert (f["code"], f["ok"]) == ("mx_partly_unresolvable", None)
    assert f["plain"] == ("One of its mail servers is listed by a name that doesn't exist. Emails still have another "
                          "way in.")


def chain(n: int) -> dict:
    """An SPF line with n includes, each resolving to a plain record."""
    out = {"TXT___AT_": ['"v=spf1 ' + " ".join(f"include:s{i}.example" for i in range(n)) + ' -all"']}
    out.update({f"TXT__s{i}.example": ['"v=spf1 ip4:192.0.2.1 -all"'] for i in range(n)})
    return out


def test_spf_lookup_limit_counts_nested_includes():
    assert found(zone("google", **chain(10)))["email_spf"]["code"] == "spf_not_covering"  # exactly 10 is allowed
    f = found(zone("google", **chain(11)))["email_spf"]
    assert (f["code"], f["ok"], f["sure"]) == ("spf_too_many_lookups", False, "seen")
    assert f["plain"] == ("Its sending-permission line makes mail services look up too many other names (11; the "
                          "limit is 10), so they give up and treat it as broken.")
    nested = {"TXT___AT_": ['"v=spf1 include:a.example mx a ptr exists:x.example -all"'],
              "TXT__a.example": ['"v=spf1 include:b.example include:c.example a:h.example mx:h.example -all"'],
              "TXT__b.example": ['"v=spf1 redirect=d.example"'],
              "TXT__c.example": ['"v=spf1 ip4:192.0.2.2 ip6:2001:db8::/32 -all"'],
              "TXT__d.example": ['"v=spf1 include:e.example include:f.example -all"'],
              "TXT__e.example": ['"v=spf1 -all"'], "TXT__f.example": ['"v=spf1 -all"'],
              "A__h.example": ["192.0.2.3"], "MX__h.example": ["1 h.example."]}
    seen = ms.spf_walk(D, txt_value(nested["TXT___AT_"][0]), zone("google", **nested))
    # top: include, mx, a, ptr, exists = 5; a.example: 2 includes + a + mx = 4; b: redirect = 1; d: 2 includes = 2
    assert (seen.lookups, seen.all) == (12, "-")


def test_spf_loops_dead_includes_voids_and_depth_are_caught_without_hanging():
    loop = {"TXT___AT_": ['"v=spf1 include:a.example -all"'], "TXT__a.example": ['"v=spf1 include:_AT_ -all"']}
    loop["TXT__a.example"] = [f'"v=spf1 include:{D} -all"']
    f = found(zone("google", **loop))["email_spf"]
    assert (f["code"], f["ok"]) == ("spf_loop", False)
    assert f["plain"] == ("Its sending-permission line refers back to itself in a circle, so mail services treat it as "
                          "broken.")
    f = found(zone("google", TXT___AT_=['"v=spf1 include:gone.example -all"']))["email_spf"]
    assert (f["code"], f["ok"]) == ("spf_include_broken", False)
    assert f["plain"] == ("Its sending-permission line refers to another name that has no working sending-permission "
                          "line of its own, so mail services treat it as broken.")
    f = found(zone("google", TXT___AT_=['"v=spf1 a:n1.example a:n2.example mx:n3.example -all"']))["email_spf"]
    assert (f["code"], f["ok"]) == ("spf_too_many_voids", False)
    assert f["plain"] == ("Its sending-permission line refers to 3 names that don't exist (the limit is 2), so mail "
                          "services may treat it as broken.")
    deep = {"TXT___AT_": ['"v=spf1 redirect=d0.example"']}
    deep.update({f"TXT__d{i}.example": [f'"v=spf1 redirect=d{i + 1}.example"'] for i in range(40)})
    dns = zone("google", **deep)
    f = found(dns)["email_spf"]
    assert f["ok"] is False and f["code"] in ("spf_too_deep", "spf_too_many_lookups")
    assert len([q for q in dns.queries if q[1] == "TXT" and q[0].startswith("d")]) <= ms.SPF_MAX_DEPTH + 1


def test_spf_question_cap_macros_missing_all_and_split_strings():
    wide = {"TXT___AT_": ['"v=spf1 ' + " ".join(f"a:w{i}.example" for i in range(60)) + ' -all"']}
    wide.update({f"A__w{i}.example": ["192.0.2.1"] for i in range(60)})
    dns = zone("google", **wide)
    assert found(dns)["email_spf"]["code"] == "spf_too_many_lookups"
    assert len([q for q in dns.queries if q[0].startswith("w")]) <= ms.SPF_MAX_QUERIES
    f = found(zone("google", TXT___AT_=['"v=spf1 exists:%{i}.rbl.example -all"']))["email_spf"]
    assert (f["code"], f["ok"], f["sure"]) == ("spf_unsure", None, "couldnt_check")
    f = found(zone("google", TXT___AT_=['"v=spf1 ip4:192.0.2.1"']))["email_spf"]
    assert (f["code"], f["ok"]) == ("spf_no_all", None)
    assert f["plain"] == ("Its sending-permission line doesn't say what to do with other servers, so it protects very "
                          "little.")
    f = found(zone("google", TXT___AT_=['"v=spf1 include:_spf.goo" "gle.com ~all"']))["email_spf"]
    assert f["code"] == "spf_ok_soft"
    assert f["plain"] == ("It says which servers may send its email, and tells mail services to treat all others as "
                          "suspicious.")
    hard = found(zone("secureserver"))["email_spf"]
    assert hard["plain"] == "It says which servers may send its email, and tells mail services to refuse all others."


@pytest.mark.parametrize("broken,check", [(D, "email_mx"), (D, "email_spf"), (f"_dmarc.{D}", "email_dmarc")])
def test_a_lookup_that_fails_on_our_side_is_never_blamed_on_them(broken, check):
    dns = zone("google")
    dns.errors.add(broken)
    f = found(dns)[check]
    assert (f["ok"], f["sure"], f["plain"]) == (None, "couldnt_check", OUR_SIDE)
    dns = zone("google")
    dns.errors.add("_spf.google.com")  # the line is there, but we couldn't follow it
    f = found(dns)["email_spf"]
    assert (f["ok"], f["sure"], f["code"]) == (None, "couldnt_check", "spf_unsure")
    dns = zone("google")
    dns.errors.add("smtp.google.com")
    f = found(dns)["email_mx"]
    assert (f["ok"], f["sure"], f["code"]) == (None, "couldnt_check", "mx_couldnt_check")


def test_dmarc_reject_reports_parent_and_subdomain_rule():
    f = found(zone("google", **{"TXT___dmarc._AT_": ['"v=DMARC1; p=reject; rua=mailto:r@shop.example"']}))["email_dmarc"]
    assert (f["code"], f["ok"]) == ("dmarc_reject", True)
    assert f["plain"] == ("It is protected against fake emails in its name: they are refused. Reports about it are "
                          "sent to an address its owner chose.")
    sub = FakeDnsResolver({("mail.shop.example", "MX"): ["1 smtp.google.com."], ("smtp.google.com", "A"): ["1.1.1.1"],
                           ("_dmarc.shop.example", "TXT"): ['"v=DMARC1; p=reject; sp=none"']})
    f = found(sub, "mail.shop.example")["email_dmarc"]
    assert (f["code"], f["ok"]) == ("dmarc_none", None) and "set on its parent name" in f["plain"]


def test_dkim_withdrawn_half_set_up_and_wildcards():
    f = found(zone("google", **{"TXT__google._domainkey._AT_": ['"v=DKIM1; p="']}))["email_dkim"]
    assert (f["code"], f["ok"]) == ("dkim_revoked", None)
    assert f["plain"] == "It has a signing key for its emails, but the key has been switched off (withdrawn)."
    half = zone("microsoft", **{"TXT__selector1._domainkey._AT_": None,
                                "CNAME__selector1._domainkey._AT_": ["selector1-shop._domainkey.t.onmicrosoft.com."]})
    f = found(half)["email_dkim"]
    assert (f["code"], f["ok"], f["sure"]) == ("dkim_half", None, "not_seen")
    assert f["plain"] == ("Signing is set up for its emails, but the key it points to isn't published. Signing may "
                          "not be switched on yet.")
    half.set("selector1-shop._domainkey.t.onmicrosoft.com", "TXT", ['"v=DKIM1; p=MIIB"'])
    assert found(half)["email_dkim"]["code"] == "dkim_found"

    class Wildcard(FakeDnsResolver):  # like example.com: ANY label under _domainkey answers
        def lookup(self, name, rtype):
            if name.endswith(f"._domainkey.{D}") and rtype == "TXT":
                return type(super().lookup(name, rtype))("ok", ('"v=DKIM1; p=MIIB"',))
            return super().lookup(name, rtype)

    f = found(Wildcard(zone("google").records))["email_dkim"]
    assert (f["code"], f["ok"], f["sure"]) == ("dkim_couldnt_check", None, "couldnt_check")


def test_a_shop_on_a_subdomain_is_judged_by_its_domains_email():
    dns = zone("google")
    dns.set(D, "NS", ["ns1.example."])
    dns.set(f"meera.{D}", "A", ["93.184.216.34"])
    assert found(dns, f"meera.{D}")["email_mx"]["domain"] == D
    assert found(dns, f"www.{D}")["email_mx"]["domain"] == D
    dns.set(f"blog.{D}", "CNAME", ["hosted.example."])  # an alias answers NS questions for its target: not a domain
    dns.set(f"blog.{D}", "NS", ["ns.hosted.example."])
    assert found(dns, f"blog.{D}")["email_mx"]["domain"] == D


def test_every_finding_says_how_sure_it_is():
    for dns in (zone("google"), zone(None), zone("titan", TXT___AT_=None)):
        for f in ms.mail_findings(D, dns):
            assert f["sure"] in ("seen", "not_seen", "couldnt_check") and f["plain"] and f["code"]


# ---------- websites ----------

def seen(**kw) -> ws.Seen:
    base = dict(host="shop.example", dns="ok", ips=("93.184.216.34",), fetch="ok", status=200, seconds=0.4, tls="ok",
                cert_days=60, http="redirects_https", http_to="shop.example")
    return ws.Seen(**{**base, **kw})


WARN = ", so browsers show a warning instead of the site."
WEB = [  # (what we saw, check, code, ok, sure, exact plain words)
    (dict(dns="nxdomain", ips=()), "address", "addr_nxdomain", False, "not_seen",
     "The address doesn't lead anywhere: this name isn't set up on the internet."),
    (dict(dns="nodata", ips=()), "address", "addr_nodata", False, "not_seen",
     "The name exists, but it doesn't lead to a website server."),
    (dict(dns="error", ips=()), "address", "addr_couldnt_check", None, "couldnt_check", OUR_SIDE),
    (dict(), "address", "addr_ok", True, "seen", "The address leads to a website server."),
    (dict(), "https", "web_ok", True, "seen", "The home page answered over a secure connection (code 200)."),
    (dict(final_host="www.shop.example"), "https", "web_ok", True, "seen",
     "The home page answered over a secure connection (code 200) (after sending us on to www.shop.example)."),
    (dict(), "plain_http", "http_redirects", True, "seen",
     "Visitors who type the address without https are sent to the secure site."),
    (dict(http="serves", http_to="200"), "plain_http", "http_no_redirect", None, "seen",
     "The site also answers on plain http without sending visitors to the secure version."),
    (dict(fetch="timeout", status=None, tls="", cert_days=None, http="timeout"), "https", "web_timeout", False, "seen",
     "The name leads to a server, but nothing answered in time."),
    (dict(fetch="refused", status=None, tls="refused", cert_days=None, http="closed"), "https", "web_refused", False,
     "seen", "The name leads to a server, but it didn't accept a secure connection."),
    (dict(fetch="refused", status=None, tls="refused", cert_days=None, http="serves", http_to="200"), "https",
     "web_http_only", False, "seen",
     "This site answers only on plain http, with no padlock: browsers warn visitors that it is not secure."),
    (dict(fetch="cert", status=None, tls="expired", cert_days=None), "https", "cert_expired", False, "seen",
     "The security certificate has expired" + WARN),
    (dict(fetch="cert", status=None, tls="wrong_host", cert_days=None), "https", "cert_wrong_host", False, "seen",
     "The security certificate belongs to a different name" + WARN),
    (dict(fetch="cert", status=None, tls="self_signed", cert_days=None), "https", "cert_self_signed", False, "seen",
     "The security certificate was made by the site itself, not by a trusted authority" + WARN),
    (dict(fetch="cert", status=None, tls="untrusted", cert_days=None), "https", "cert_untrusted", False, "seen",
     "The security certificate comes from an authority browsers don't trust" + WARN),
    (dict(fetch="cert", status=None, tls="not_yet_valid", cert_days=None), "https", "cert_not_yet_valid", False, "seen",
     "The security certificate isn't valid yet (its start date is in the future)" + WARN),
    (dict(fetch="cert", status=None, tls="", cert_days=None), "https", "cert_bad_cert", False, "seen",
     "The security certificate didn't pass our check, so browsers are likely to show a warning instead of the site."),
    (dict(cert_days=60), "certificate", "cert_days_ok", True, "seen", "The security certificate is good for 60 more days."),
    (dict(cert_days=14), "certificate", "cert_days_ok", True, "seen", "The security certificate is good for 14 more days."),
    (dict(cert_days=13), "certificate", "cert_expiring", False, "seen", "The security certificate runs out in 13 days."),
    (dict(status=404), "https", "web_client_error", False, "seen",
     "The site answered securely, but its home page wasn't there (code 404)."),
    (dict(status=503), "https", "web_server_error", False, "seen",
     "The site answered securely, but with an error on its side (code 503)."),
    (dict(status=403), "https", "web_turned_away", None, "couldnt_check",
     "The site answered securely but turned our check away (code 403). It may still open for ordinary visitors."),
    (dict(fetch="loop", status=None), "https", "web_redirect_loop", False, "seen",
     "The address keeps sending visitors on to another page without ever arriving (too many redirects)."),
    (dict(seconds=7.2), "speed", "web_slow", None, "seen",
     "It answered, but slowly (about 7 seconds). Visitors may give up waiting."),
    (dict(fetch="private", status=None, note="That address points to a private network, so we won't open it."), "https",
     "web_private", None, "couldnt_check", "That address points to a private network, so we won't open it."),
    (dict(fetch="blocked", status=None), "https", "web_blocked", None, "couldnt_check",
     "The address sends visitors on to a page we don't open (not secure, or not public), so we stopped there."),
    (dict(fetch="error", status=None, tls="ok"), "https", "web_error", None, "couldnt_check",
     "We reached the server, but the answer broke off before we could read it."),
    # found on the real example.com: the page opened, but a second look with another trust list disagreed
    (dict(tls="untrusted", cert_days=None), "https", "web_ok", True, "seen",
     "The home page answered over a secure connection (code 200)."),
    # found on the real http.badssl.com: the secure address hands visitors back to plain http
    (dict(fetch="to_http", status=None, http="serves", http_to="200"), "https", "web_https_to_http", False, "seen",
     "The secure address sends visitors back to plain http, with no padlock: browsers warn visitors that it is "
     "not secure."),
    (dict(hsts=True), "hsts", "hsts_present", True, "seen",
     "It tells browsers to always use the secure version (extra protection)."),
]


@pytest.mark.parametrize("saw,check,code,ok,sure,plain", WEB, ids=[f"{w[1]}-{w[2]}-{i}" for i, w in enumerate(WEB)])
def test_website_matrix(saw, check, code, ok, sure, plain):
    f = {x["check"]: x for x in ws.judge(seen(**saw))}[check]
    assert (f["code"], f["ok"], f["sure"], f["plain"]) == (code, ok, sure, plain)
    assert "your site works" not in f["plain"].lower() and "93.184" not in f["plain"]
    if ok is False:
        assert f["action"] == "explain" and f["steps"]


def test_slow_is_never_called_broken_and_fast_gets_no_speed_line():
    slow = {f["check"]: f for f in ws.judge(seen(seconds=19.0))}
    assert slow["https"]["ok"] is True and slow["speed"]["ok"] is None
    assert "speed" not in {f["check"] for f in ws.judge(seen(seconds=4.9))}
    assert "hsts" not in {f["check"] for f in ws.judge(seen())}  # absent HSTS is not a finding at all


def test_www_and_the_bare_name_disagreeing():
    bad = seen(host="www.shop.example", fetch="refused", status=None)
    f = {x["check"]: x for x in ws.judge(seen(), bad)}["www"]
    assert (f["code"], f["ok"], f["sure"]) == ("www_disagree", False, "seen")
    assert f["plain"] == "shop.example opens, but www.shop.example doesn't, so visitors who type that one won't arrive."
    f = {x["check"]: x for x in ws.judge(seen(), seen(host="www.shop.example", dns="nxdomain", ips=(), fetch=""))}["www"]
    assert (f["code"], f["ok"], f["sure"]) == ("www_not_set_up", None, "not_seen")
    f = {x["check"]: x for x in ws.judge(seen(fetch="timeout", status=None), seen(host="www.shop.example"))}["www"]
    assert f["plain"].startswith("www.shop.example opens, but shop.example doesn't")
    for same in (seen(host="www.shop.example"), seen(host="www.shop.example", dns="error", ips=(), fetch="")):
        assert "www" not in {x["check"] for x in ws.judge(seen(), same)}


def test_international_names_are_shown_readably():
    from app.routers.proof import clean_address

    assert clean_address("https://Bücher.example/x") == "xn--bcher-kva.example"
    assert ws.readable("xn--bcher-kva.example") == "bücher.example" and ws.readable("shop.example") == "shop.example"
    twin = seen(host="www.xn--bcher-kva.example", fetch="refused", status=None)
    f = {x["check"]: x for x in ws.judge(seen(host="xn--bcher-kva.example"), twin)}["www"]
    assert "bücher.example opens, but www.bücher.example doesn't" in f["plain"]
    assert ws.readable("xn--zz-broken-.example") == "xn--zz-broken-.example"  # never crashes on a bad name


class Web:
    """A fetcher that plays back one situation."""

    def __init__(self, page=None, raises=None, tls=None, http=("redirects_https", "shop.example")):
        self.page, self.raises, self.tls, self.http, self.calls = page, raises, tls or TlsSeen("ok"), http, []

    def get(self, url):
        self.calls.append(("get", url))
        if self.raises:
            raise self.raises
        return self.page

    def tls_look(self, host):
        self.calls.append(("tls", host))
        return self.tls

    def http_first(self, host):
        self.calls.append(("http", host))
        return self.http


def page(status=200, **kw):
    from app.checks.safe_fetch import Page

    return Page(status, "", "https://shop.example/", **kw)


def test_observe_reads_only_the_home_page_and_classifies_what_it_saw():
    from datetime import UTC, datetime, timedelta

    dns = FakeDnsResolver({("shop.example", "A"): ["93.184.216.34"]})
    web = Web(page(seconds=0.31, hsts=True), tls=TlsSeen("ok", datetime.now(UTC) + timedelta(days=30, hours=1)))
    s = ws.observe("shop.example", dns, web)
    assert (s.dns, s.fetch, s.status, s.tls, s.cert_days, s.http, s.hsts) == ("ok", "ok", 200, "ok", 30,
                                                                              "redirects_https", True)
    assert web.calls == [("get", "https://shop.example/"), ("tls", "shop.example"), ("http", "shop.example")]
    s = ws.observe("shop.example", dns, Web(page(None, kind="cert", cert_valid=False), tls=TlsSeen("expired")))
    assert (s.fetch, s.tls) == ("cert", "expired")
    web = Web(page(None, kind="timeout", error="ConnectTimeout"))
    s = ws.observe("shop.example", dns, web)
    assert s.fetch == "timeout" and ("tls", "shop.example") not in web.calls  # no second wait on a dead server
    assert ws.observe("shop.example", dns, Web(raises=TooManyRedirects("x"))).fetch == "loop"
    web = Web(raises=PrivateAddress("private"))
    assert ws.observe("shop.example", dns, web).fetch == "private" and len(web.calls) == 1
    assert ws.observe("shop.example", dns, Web(raises=Refused("no"))).fetch == "blocked"
    gone = ws.observe("nowhere.example", FakeDnsResolver({("x.example", "A"): ["1.1.1.1"]}), Web())
    assert gone.dns == "nxdomain"
    broken = FakeDnsResolver({})
    broken.errors.add("shop.example")
    assert ws.observe("shop.example", broken, Web()).dns == "error"


def test_www_twin_is_only_looked_at_for_a_domain_of_its_own():
    dns = FakeDnsResolver({("shop.example", "A"): ["93.184.216.34"]})
    assert ws.twin_of("shop.example", dns) is None and ws.twin_of("www.shop.example", dns) == "shop.example"
    dns.set("shop.example", "NS", ["ns1.example."])
    assert ws.twin_of("shop.example", dns) == "www.shop.example"
    web = Web(page(), tls=TlsSeen("ok"))
    f = {x["check"]: x for x in ws.web_findings("shop.example", dns, web)}
    assert f["www"]["code"] == "www_not_set_up"


def test_the_handshake_trusts_the_same_authorities_as_the_page_fetch(monkeypatch):
    """Found on the real example.com: two different trust lists gave "page opened" and "certificate not trusted"."""
    import certifi

    from app.checks import safe_fetch

    asked = {}
    real = ssl.create_default_context
    monkeypatch.setattr(ssl, "create_default_context", lambda *a, **kw: asked.update(kw) or real(*a, **kw))
    safe_fetch.tls_context()
    assert asked.get("cafile") == certifi.where()
    web = Web(raises=safe_fetch.NotHttps("We only open secure (https) web addresses."), http=("serves", "200"))
    assert ws.observe("shop.example", FakeDnsResolver({("shop.example", "A"): ["93.184.216.34"]}), web).fetch == "to_http"


def cert_error(code: int) -> ssl.SSLCertVerificationError:
    e = ssl.SSLCertVerificationError("certificate verify failed")
    e.verify_code = code
    return e


@pytest.mark.parametrize("error,kind", [
    (cert_error(10), "expired"), (cert_error(9), "not_yet_valid"), (cert_error(18), "self_signed"),
    (cert_error(19), "untrusted"), (cert_error(20), "untrusted"), (cert_error(62), "wrong_host"),
    (cert_error(99), "bad_cert"), (TimeoutError(), "timeout"), (ConnectionRefusedError(), "refused"),
    (ssl.SSLError("wrong version number"), "no_tls"), (OSError("unreachable"), "refused")])
def test_why_a_secure_handshake_failed(error, kind):
    assert tls_kind(error) == kind


@pytest.mark.parametrize("answer,want", [
    (httpx.Response(301, headers={"location": "https://shop.example/"}), ("redirects_https", "shop.example")),
    (httpx.Response(302, headers={"location": "http://other.example/"}), ("redirects_http", "other.example")),
    (httpx.Response(200, text="hello"), ("serves", "200")), (httpx.Response(500), ("error", "500"))])
def test_plain_http_look_is_one_pinned_request_with_nothing_followed(answer, want):
    asked = []

    def handler(request):
        asked.append((str(request.url), request.headers["host"]))
        return answer

    web = SafeWeb(lambda _h: True, resolve=lambda _h: ["93.184.216.34"], transport=httpx.MockTransport(handler))
    assert web.http_first("shop.example") == want
    assert asked == [("http://93.184.216.34/", "shop.example")]
    private = SafeWeb(lambda _h: True, resolve=lambda _h: ["10.0.0.8"], transport=httpx.MockTransport(handler))
    with pytest.raises(PrivateAddress):
        private.http_first("shop.example")
    with pytest.raises(PrivateAddress):
        private.tls_look("shop.example")


def test_safe_web_reports_time_hsts_and_timeouts():
    def handler(request):
        if request.headers["host"] == "slow.example":
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, text="ok", headers={"strict-transport-security": "max-age=600"})

    web = SafeWeb(lambda _h: True, resolve=lambda _h: ["93.184.216.34"], transport=httpx.MockTransport(handler))
    assert web.get("https://shop.example/").hsts is True
    assert web.get("https://slow.example/").kind == "timeout"


# ---------- the public tool end to end ----------

def test_check_any_address_only_explains(monkeypatch):
    from app.routers.proof import address_results

    dns = zone("google", TXT___AT_=None, **{"TXT___dmarc._AT_": None})
    results = address_results(D, dns, Web(page(), tls=TlsSeen("ok")))
    assert {r["check"] for r in results} >= {"address", "https", "email_mx", "email_spf", "email_dkim", "email_dmarc"}
    for r in results:
        assert set(r) >= {"check", "ok", "plain", "detail", "sure", "code", "steps", "action"}
        assert r["action"] in ("explain", "none")  # never "fix": nothing is offered or applied on an outside site
        assert "fix_id" not in r
    spf = next(r for r in results if r["check"] == "email_spf")
    assert "_spf.google.com" in spf["steps"] and "secureserver" not in spf["steps"] and "titan" not in spf["steps"]


# ---------- the saved real answers (tests/fixtures/network, from `pytest -m network`), replayed offline ----------

def real_answers():
    import json
    from pathlib import Path

    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(__file__).parent / "fixtures" / "network").glob("*.json"))]


class Replay:
    """Answers exactly what the real resolver answered on the day; anything else was never asked."""

    def __init__(self, asked: dict):
        self.asked = asked

    def lookup(self, name, rtype):
        from app.checks.dns_resolver import Answer

        status, values = self.asked.get(f"{name.lower().rstrip('.')} {rtype}", ["error", []])
        return Answer(status, tuple(values))


@pytest.mark.parametrize("saved", real_answers(), ids=lambda d: f"{d['kind']}-{d['host']}")
def test_saved_real_answers_still_give_the_same_findings(saved):
    if saved["kind"] == "mail":
        findings = ms.mail_findings(saved["host"], Replay(saved["dns"]))
    else:
        web = {**saved["web"], "ips": tuple(saved["web"]["ips"])}
        twin = saved.get("twin")
        findings = ws.judge(ws.Seen(**web), ws.Seen(**{**twin, "ips": tuple(twin["ips"])}) if twin else None)
    assert [[f["check"], f["code"], f["ok"], f["sure"]] for f in findings] == saved["findings"]
    assert {f["check"]: f["plain"] for f in findings} == saved["plain"]


def test_there_is_a_saved_real_answer_for_each_kind_of_setup():
    hosts = {d["host"] for d in real_answers()}
    assert hosts >= {"google.com", "microsoft.com", "zoho.com", "launchwitness.com", "example.com", "titan.email",
                     "expired.badssl.com", "wrong.host.badssl.com", "self-signed.badssl.com",
                     "untrusted-root.badssl.com", "http.badssl.com", "github.com"}
