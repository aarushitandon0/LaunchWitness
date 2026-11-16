# Checks matrix (S11b)

Every scenario we can meet → what we show → how sure we are → what the Doctor may do → the test that proves it.

- **Sure:** `seen` (we read it) · `not seen` (we looked, it wasn't there) · `couldn't check` (our lookup failed, or it can't be looked up).
- **Shown as:** ✓ good (`ok: true`) · ✕ a real problem (`ok: false`, the only kind that sends a "Watch this address" email) · – a note or "not sure" (`ok: null`).
- **Doctor:** *explain* = plain words plus the email service's own steps, nothing offered or applied · *fix* = a playbook fix, our shops only · *needs you* = exact plain steps for the owner.
- Tests live in `backend/tests/`. `matrix` = `test_s11b_matrix.py`, `providers` = `test_s11b_doctor_providers.py`, `network` = `test_s11b_network.py`, `gaps` = `test_s11b_gaps.py`.
- Code: `app/checks/web_setup.py` (websites), `app/checks/mail_setup.py` (email; the one provider table is `SERVICES`), `app/checks/dns_resolver.py::lookup` (every answer carries ok / no record / no such name / *our lookup failed*).

## 1. Any website ("Check any address", "Watch this address")

Outside sites are **explain only**: no fix is ever offered or applied (`matrix::test_check_any_address_only_explains`).
All rows below are proven by `matrix::test_website_matrix` unless another test is named.

| Scenario | What we show | Sure | Shown | Doctor |
|---|---|---|---|---|
| Name doesn't exist | The address doesn't lead anywhere: this name isn't set up on the internet. | not seen | ✕ | explain |
| Name exists, no website address | The name exists, but it doesn't lead to a website server. | not seen | ✕ | explain |
| **Our** DNS lookup failed | We couldn't read this just now (the problem was on our side, not theirs)… | couldn't check | – | none |
| Resolves, nothing answers in time | The name leads to a server, but nothing answered in time. | seen | ✕ | explain |
| Resolves, secure connection refused | The name leads to a server, but it didn't accept a secure connection. | seen | ✕ | explain |
| http only, no https | This site answers only on plain http, with no padlock: browsers warn visitors that it is not secure. | seen | ✕ | explain |
| https sends visitors back to http | The secure address sends visitors back to plain http, with no padlock… | seen | ✕ | explain |
| http → https redirect | Visitors who type the address without https are sent to the secure site. | seen | ✓ | none |
| http also served, no redirect | The site also answers on plain http without sending visitors to the secure version. | seen | – | explain |
| Certificate expired | The security certificate has expired, so browsers show a warning instead of the site. | seen | ✕ | explain |
| Certificate for another name | The security certificate belongs to a different name, so browsers show a warning… | seen | ✕ | explain |
| Self-signed certificate | The security certificate was made by the site itself, not by a trusted authority… | seen | ✕ | explain |
| Untrusted root | The security certificate comes from an authority browsers don't trust… | seen | ✕ | explain |
| Not valid yet / other certificate failure | …isn't valid yet… / …didn't pass our check, so browsers are likely to show a warning… | seen | ✕ | explain |
| Page opened but a second handshake disagreed | (no certificate claim; the page result stands) | seen | ✓ | none |
| Valid certificate, ≥ 14 days left | The security certificate is good for N more days. | seen | ✓ | none |
| Valid certificate, < 14 days left | The security certificate runs out in N days. | seen | ✕ | explain |
| 200–399 | The home page answered over a secure connection (code N). *(never "your site works")* | seen | ✓ | none |
| 401 / 403 / 429 | The site answered securely but turned our check away (code N). It may still open for ordinary visitors. | couldn't check | – | none |
| Other 4xx | The site answered securely, but its home page wasn't there (code N). | seen | ✕ | explain |
| 5xx | The site answered securely, but with an error on its side (code N). | seen | ✕ | explain |
| Too many / looping redirects | The address keeps sending visitors on to another page without ever arriving (too many redirects). | seen | ✕ | explain |
| Redirect to another host | …(after sending us on to other.example) | seen | ✓ | none |
| Redirect to something we don't open | The address sends visitors on to a page we don't open (not secure, or not public), so we stopped there. | couldn't check | – | none |
| Private network address | That address points to a private network, so we won't open it. | couldn't check | – | none |
| Answer broke off | We reached the server, but the answer broke off before we could read it. | couldn't check | – | none |
| Slow (> 5 s) but answered | It answered, but slowly (about N seconds). Visitors may give up waiting. *(never "broken")* `matrix::test_slow_is_never_called_broken…` | seen | – | explain |
| www and bare name: one opens, one fails | A opens, but B doesn't, so visitors who type that one won't arrive. `matrix::test_www_and_the_bare_name_disagreeing` | seen | ✕ | explain |
| www not set up at all | A opens, but B isn't set up, so visitors who type that one won't arrive. | not seen | – | explain |
| HSTS present | It tells browsers to always use the secure version (extra protection). *(absent = no line at all)* | seen | ✓ | none |
| International name (`xn--…`) | Shown readably (bücher.example) in every sentence and as `shown_as`. `matrix::test_international_names_are_shown_readably` | — | — | — |
| Dangling alias | Possible dangling record: … points to …, which doesn't exist. `test_s10_watchdog.py` | seen | ✕ | explain |

How a failed handshake is named: `matrix::test_why_a_secure_handshake_failed`. The plain-http look is one pinned request with nothing followed and
the same private-network guard: `matrix::test_plain_http_look_is_one_pinned_request_with_nothing_followed`.

**Our own shops** keep the stricter rule: the page must carry the shop's `lw-shop` marker, so a parked or wrong page fails
(`test_s9_phase3_proof.py::test_https_needs_the_shop_marker`).

## 2. Email, provider-aware (any address)

**Provider detection** (from the mail-server names only; `matrix::test_provider_is_detected_and_a_healthy_setup_is_all_good`, 8 services):

| Service | Recognised by mail servers ending in | Its SPF name | Signing labels tried | Checked on real DNS |
|---|---|---|---|---|
| Google Workspace (Gmail) | `google.com`, `googlemail.com` | `_spf.google.com` | `google` | yes (google.com) |
| Microsoft 365 (Outlook) | `protection.outlook.com`, `mx.microsoft` | `spf.protection.outlook.com` (or `secureserver.net` when bought through GoDaddy) | `selector1`, `selector2` | yes (microsoft.com) |
| Zoho Mail | `zoho.com`, `zohomail.com` | `zoho.com`, `zohomail.com` and names under them | `zmail`, `zoho` | yes (zoho.com) |
| Zoho Mail (India) | `zoho.in`, `zohomail.in` | `zoho.in`, `zohomail.in` and names under them | `zmail`, `zoho` | yes (zoho.in) |
| GoDaddy Professional Email | `secureserver.net` | `secureserver.net` | (ours: `titan1`, `mail`) | yes (launchwitness.com) |
| Titan Email | `titan.email` | `spf.titan.email` | `titan1` | yes (titan.email) |
| Hostinger Email | `hostinger.com`, `hostinger.in` | `_spf.mail.hostinger.com` | `hostingermail-a/b/c` | **no**: from memory of Hostinger's docs |
| Cloudflare Email Routing | `mx.cloudflare.net` | `_spf.mx.cloudflare.net` | `cf2024-1` | **no**: from memory of Cloudflare's docs |
| Null MX (`0 .`) | — | — | none (not applicable) | yes (example.com) |
| No MX | — | — | none (not applicable) | yes (neverssl.com) |
| Unknown provider | anything else | **no values are ever given** | none (we don't guess) | yes (jvns.ca) |
| Two services mixed | — | no values given | none | offline only |

| Scenario | What we show | Sure | Shown | Doctor | Test (`matrix::`) |
|---|---|---|---|---|---|
| Healthy, known service | Emails to this address have somewhere to go: *Service*. | seen | ✓ | none | `test_provider_is_detected…` |
| Healthy, unknown service | …somewhere to go (an email service we don't recognise). | seen | ✓ | none | `test_null_mx_no_mx_unknown_and_mixed` |
| Null MX | This address says it doesn't accept email. | seen | ✕ | explain (deliberate setting) | same |
| No MX | This address has no mail servers listed, so emails sent to it will almost certainly not arrive. | not seen | ✕ | explain | same |
| Two services mixed | Emails to this address are split between two different email services (A and B)… | seen | – | explain, no values | same |
| MX is an alias (CNAME) | Its mail server name is an alias for another name. The rules for email don't allow that… | seen | – | explain | `test_mx_alias_ip_literal_and_one_dead_server` |
| MX is an IP literal | Its mail server is listed as a bare number instead of a name, which mail services refuse. | seen | ✕ | explain | same |
| All MX hosts don't resolve | Its mail servers are listed by names that don't exist, so emails to it can't be delivered. | seen | ✕ | explain, that service's servers | `test_mail_servers_that_do_not_exist` × 8 |
| One MX host doesn't resolve | One of its mail servers is listed by a name that doesn't exist. Emails still have another way in. | seen | – | explain | `test_mx_alias…` |
| SPF missing | It doesn't say which servers may send its email, so its emails may land in spam. | not seen | ✕ | explain, that service's line | `test_each_problem_on_each_provider` × 8 |
| More than one SPF record | It has more than one sending-permission line. Mail services treat that as an error… | seen | ✕ | explain | same × 8 |
| SPF `+all` | …allows every server in the world to send as this address, so it protects nothing. | seen | ✕ | explain | same × 8 |
| SPF `?all` | …takes no position on other servers, so it protects nothing. | seen | ✕ | explain | same × 8 |
| SPF syntax error | Its sending-permission line has a mistake in it, so mail services can't read it. | seen | ✕ | explain | same × 8 |
| SPF over 10 lookups (nested) | …look up too many other names (N; the limit is 10)… | seen | ✕ | explain | `test_spf_lookup_limit_counts_nested_includes` |
| SPF over 2 empty lookups | …refers to N names that don't exist (the limit is 2)… | seen | ✕ | explain | `test_spf_loops_dead_includes_voids…` |
| SPF include loop / too deep | …refers back to itself in a circle… / …nested too deeply… | seen | ✕ | explain | same |
| SPF includes a name with no SPF | …refers to another name that has no working sending-permission line of its own… | seen | ✕ | explain | same |
| SPF doesn't name the detected service | It has a sending-permission line, but we didn't see *Service* named in it. If this address sends email through *Service*… | not seen | – | explain | `test_spf_that_does_not_name…` × 8 |
| SPF with no `all` | …doesn't say what to do with other servers, so it protects very little. | seen | – | explain | `test_spf_question_cap_macros…` |
| SPF `~all` / `-all` | …tells mail services to treat all others as suspicious / to refuse all others. | seen | ✓ | none | same |
| SPF with a macro, or an include we couldn't follow | …we couldn't follow everything it refers to just now… | couldn't check | – | none | same, `test_a_lookup_that_fails_on_our_side…` |
| SPF split over several strings | read as one line | — | — | — | same |
| DMARC missing | It isn't protected against fake emails in its name. | not seen | ✕ | explain | `test_each_problem_on_each_provider` × 8 |
| More than one DMARC record | It has more than one fake-email protection line, so mail services ignore them all. | seen | ✕ | explain | same × 8 |
| DMARC syntax | Its fake-email protection line has a mistake in it, so mail services ignore it. | seen | ✕ | explain | same × 8 |
| DMARC `p=none` | It only watches for fake emails in its name (monitoring only): fake mail in its name still gets through. | seen | – | explain | same × 8 |
| DMARC quarantine / reject | It is protected against fake emails in its name: they are sent to spam / refused. | seen | ✓ | none | `test_dmarc_reject_reports_parent…` |
| DMARC reports address | adds "Reports about it are sent to an address its owner chose." | seen | (info) | none | same |
| DMARC on the parent name (`sp=`) | "(the rule is set on its parent name)" | seen | as policy | — | same |
| DKIM key found | Its emails can be signed: we found a signing key. | seen | ✓ | none | `test_provider_is_detected…` |
| DKIM not found under known labels | **We couldn't check** whether its emails are signed: a signing key can only be looked up by its private label… *(never "missing")* | couldn't check | – | explain, that service's steps | `test_dkim_is_never_called_missing` × 8 |
| DKIM key withdrawn (`p=` empty) | It has a signing key for its emails, but the key has been switched off (withdrawn). | seen | – | explain | `test_dkim_withdrawn_half_set_up_and_wildcards` |
| DKIM alias with no key behind it | Signing is set up for its emails, but the key it points to isn't published… | not seen | – | explain | same |
| Wildcard answers for any label | We couldn't check… | couldn't check | – | explain | same |
| No email on this address | This address isn't set up for email, so there is no email signing to check. | seen | – | none | `test_null_mx_no_mx_unknown_and_mixed` |
| **Our** lookup failed (any of MX / SPF / DMARC) | We couldn't read this just now (the problem was on our side, not theirs)… | couldn't check | – | none | `test_a_lookup_that_fails_on_our_side…` × 3 |
| A shop on a subdomain | judged by its domain's email (an alias is not a domain) | — | — | — | `test_a_shop_on_a_subdomain…` |

Advice never names another service's settings: `test_each_problem_on_each_provider` asserts it for all 8 services × 9 problems, and an unknown
service gets the sentence "We don't recognise the email service this address uses, so we won't guess its settings…" and no values.

## 3. Our own shops: the Doctor

| Scenario | What happens | Test |
|---|---|---|
| The seller's email is on another service (Google, Microsoft, Zoho, Zoho India, Titan, Hostinger, Cloudflare, unknown) and an email check fails | **Needs you**, written by code (the model isn't asked): "Email for your address is now handled by *Service*… we never change another email service's settings", plus that service's own steps. Nothing is written. | `providers::test_another_services_mail_is_explained_never_fixed_or_overwritten` (8 services × 2 checks) |
| The same, and a fix is asked for directly | The guarded write refuses; the zone is unchanged. | same |
| Our own mail servers went missing | **Fix** (`readd_mx`), re-checked. | `providers::test_our_own_missing_settings_are_still_fixed` |
| Her SPF line names us and another sender; she added a record after launch | Both are kept. | `providers::test_a_shared_spf_line_and_later_records_are_kept` |
| Mail sign-in refused | The instruction is the code's (`MAIL_SIGN_IN_REFUSED`), never the model's. | `test_s11_doctor.py` |

## 4. Real-network run (2026-11-16, from the owner's laptop)

Read-only: public DNS questions and one home-page visit each. How to run: `cd backend && ../.venv/Scripts/python -m pytest -m network tests/test_s11b_network.py -q`
(add `LW_SAVE_FIXTURES=1` to re-save `tests/fixtures/network/*.json`; email addresses in the saved answers are replaced). The saved answers are
replayed offline by `matrix::test_saved_real_answers_still_give_the_same_findings` (17 files).

| Domain | What we showed |
|---|---|
| google.com | Google Workspace · SPF good (`~all`) · signing: couldn't check (label unknown) · fake-email protection: refused |
| microsoft.com | Microsoft 365 · SPF good (`-all`, 6 lookups) · signing key found (`selector2`) · refused |
| zoho.com / zoho.in | Zoho Mail / Zoho Mail (India) · SPF good · signing: couldn't check · refused |
| launchwitness.com | GoDaddy Professional Email · SPF good (`-all`) · signing: couldn't check · sent to spam |
| titan.email | Titan Email · SPF good (7 lookups) · signing key found (`titan1`) · refused |
| example.com (mail) | says it doesn't accept email · SPF good (`-all`) · no signing to check · refused |
| neverssl.com (mail) | no mail servers · SPF missing · no signing to check · protection missing |
| jvns.ca | an email service we don't recognise · SPF `?all` (protects nothing) · couldn't check · sent to spam; steps give no values |
| expired.badssl.com | certificate expired |
| wrong.host.badssl.com | certificate belongs to a different name |
| self-signed.badssl.com | certificate made by the site itself |
| untrusted-root.badssl.com | certificate from an authority browsers don't trust |
| http.badssl.com | the secure address sends visitors back to plain http |
| neverssl.com (web) | answers only on plain http; www opens but the bare name doesn't |
| github.com | answered securely (200) · certificate good · http → https · HSTS |
| example.com (web) | answered securely (200) · certificate good · also answers on plain http with no redirect (a note) |

Not found: a domain on Cloudflare Email Routing or Hostinger Email that I could identify from public DNS alone, so those two rows are proven
offline only.

**Bugs the real run found (each got a failing offline test first, then the fix):**
1. Zoho's own SPF names (`spf.zoho.com`, `spf.zohomail.com`) weren't recognised as Zoho → "didn't see Zoho named". Names under a service's name now count.
2. example.com answers for *any* signing label (a wildcard), so we said "it has a signing key, switched off". Now: a wildcard → couldn't check; a domain with no email → "no signing to check"; an unknown service → no labels tried.
3. A blog subdomain that is an alias was judged as its own email domain. An alias is no longer treated as a domain.
4. example.com: the page opened, yet we said "certificate not trusted", because the handshake used the system's trust list and the fetch used another. Both now use the same list, and a page that opened is never called a certificate failure.
5. expired.badssl.com came out as "untrusted" for the same reason; now "expired".
6. http.badssl.com (https redirects to http) came out as a vague "page we don't open". Now its own finding.
7. Old test fixtures had a mail server with no address and an SPF line referring to a name with no SPF; both are now (correctly) reported, so the fixtures were made genuinely healthy.

**Watch job on real addresses** (`network::test_watch_job_on_real_addresses_is_read_only_and_does_not_repeat`): example.com, expired.badssl.com,
github.com. First run: one alert email, to the watcher only; second run: none. Nothing is sent to the watched domains.
