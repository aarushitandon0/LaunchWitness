# Session 9 prompt — UPI pay link, order tracking, trust and safety

Paste this as the first message of session 9.

---

Session 9: UPI pay link, order status tracking, trust and safety

**Positioning (decided in session 8.5): proof first, generation last.** Pitch: "Airo builds your website. LaunchWitness proves it can take a customer's order, fixes it when it can't, and keeps watching after launch." Every new piece below should feed the proof: the UPI-link and status-page checks are launch checks; seller-facing copy talks about "your shop is ready for customers", not "your website is generated". Infra facts: app domain `launchwitness.com`, mailbox `hello@launchwitness.com` (GoDaddy Professional Email, secureserver.net), VPS arrives Wed Nov 18, demo shop `meerasbakes.launchwitness.com`.

Follow the session ritual in CLAUDE.md: read CLAUDE.md and docs/PROGRESS.md, post a plan, and WAIT for my OK.

## Goal
Sellers need payment and order tracking, and the platform needs basic protection against abuse. No payment gateway (it needs per-seller KYC and can't be one-click). Use what Indian home sellers actually use: UPI, WhatsApp links and a simple status page.

## Scope

### Orders
1. **Order form fields** (on the session-8 template; stay generic, nothing trade-specific):
   - Date needed. Enforce `min_notice_days` on the server in India time (Asia/Kolkata): the earliest allowed date is today + notice days; no past dates; at most 60 days ahead.
   - Pickup vs delivery, offered only as the profile allows (`pickup_available`, `delivery_available`). Address is required only for delivery.
   - Quantity per item (the basket already exists).
   - "Message on the item": already shown only when `allow_item_message` is on (a profile field, default off; no presets). Keep it that way.
   - Phone (already there; keep the 10-digit check).
2. **Order ID:** `LW-` + 8 characters from an unambiguous alphabet (no 0/O/1/I), e.g. `LW-4F2K7Q9M`, from `secrets`, unique, stored next to the internal id. Store orders with a status history (status, time, who changed it).
3. **Server-side totals:** price × quantity from the saved menu, plus `delivery_fee_inr` only when delivery is chosen. Never trust client prices (the form already ignores them; keep the test). Extras can't be ordered alone (already enforced).
4. **UPI pay:** after submitting, show "Pay ₹X via UPI". On phones, a prefilled link `upi://pay?pa=<VPA>&pn=<name>&am=<amount>&cu=INR&tn=<order ID>`; on laptops, a QR of the same link. Show "Your UPI app should show: <upi_display_name>" when set. Validate the VPA format when the profile is saved (already done). If the seller has no UPI ID, say "The shop will tell you how to pay" instead. No money ever passes through us.
5. **Status page** `/o/<order id>` on the seller's own site: Received → Confirmed → Paid → Preparing → Ready / Out for delivery → **Delivered / Picked up**, or Cancelled (from any state before Delivered; if it was Paid, show "The shop will refund you on UPI"). No illegal jumps. No PII beyond the customer's first name and the items. Rate-limited per visitor; unknown IDs get a plain 404.
6. **Seller controls** on her existing owner secret link: list orders (newest first, filter by status), change status, "Mark paid" after checking her UPI app. **Test orders from the launch check are marked and hidden from this list by default.**
7. **The seller must not miss an order.** This is the biggest gap. Use only free `wa.me` links:
   - The new-order email goes to the shop mailbox **and** her personal email (`owner_email`). It includes the order ID, the status link and the pay amount.
   - The customer's success screen has **"Send this order to <shop> on WhatsApp"** (a prefilled `wa.me` link to the seller with the order ID, items and total), plus the status link and a "share" link.
   - Each order in the seller's list has **"Tell the customer on WhatsApp"**, with a ready-typed message for the current status and the status link.
8. **New launch checks** (Checker + Doctor playbook):
   - A test order produces a valid UPI link with the right amount and order ID (marked **skipped, not failed**, when the seller has no UPI ID).
   - The status page loads and reflects a status change.
   Each needs a plain-sentence Doctor explanation and an allowed fix, or is marked "cannot auto-fix" with the reason.

### Trust and safety
9. **Email verification before any real launch.** The owner's personal email is confirmed with a one-time link (store only a hash of the token; it expires after 24 h; resend is rate-limited). A real launch (not practice) is refused with a plain message until it's verified. The review screen shows whether it's verified.
10. **Claude policy check (hold, never launch).** One cheap-model call on the saved profile before a real launch: is this shop OK to put live? The reply is `{ok, reason}`, where reason is one plain sentence. If it isn't OK, the business is "held for review" and the launch stops with a plain message. Only the team (admin) can release it; Claude can never launch or release anything. If Claude is unavailable, hold rather than launch. Treat the seller's text as data (prompt-injection test). Use fixtures for OK, hold and injection; no live calls this session.
11. **"Report this shop"** link in every seller site's footer: a short form (reason + optional note, honeypot, per-visitor limit). It's stored, audited and emailed to the team mailbox.
12. **Admin pause switch** (team only, on the report page): a paused shop shows a plain "This shop is paused" page and refuses new orders; existing status pages still open. The owner gets an email. Unpause is admin-only. Everything is audited.

## Rules
- No payment gateway, SMS or WhatsApp Business API. Note "Connect Razorpay (after seller KYC)" as future work in SPEC and the judge Q&A (already added in session 8; keep it accurate).
- Works in fixture mode; no live Claude calls needed this session. The policy-check fixtures are hand-written (`_note`) until captured on the owner's laptop.
- Never print or read .env, never paste keys.
- Template stays generic: nothing specific to one seller or trade; no per-business CSS; no "Verified" label anywhere.

## Done when
- Tests cover: notice-date enforcement (in India time, including around midnight), server-side totals incl. the delivery fee only for delivery, UPI link encoding (spaces, ₹ amounts, special characters in names, `&` and `#`), order ID unguessability (alphabet, length, uniqueness, no sequential IDs on public pages), status transitions (no illegal jumps), the status page leaking no PII (no phone, address or surname), owner-link auth on every seller endpoint, test orders hidden from the seller's list, the personal-email copy of new orders, both WhatsApp hand-off links, the 2 new checks passing, failing and skipping correctly, email verification blocking a real launch, the policy check holding (and never releasing), report → stored + emailed, and pause → no new orders.
- Full suite green (same 2 skipped).
- Screenshots of form → pay → status page → seller order list on mobile and desktop saved to `docs/screenshots/s9/`, using at least 3 of the session-8 gallery sellers (one with no UPI ID).
- Update PROGRESS + BUILD_LOG, save the transcript, rebuild replay, run the secret scan, open the PR and merge once tests pass.

**Reminder:** M1 (VPS) happens on Wed Nov 18 when the free VPS arrives (don't buy one). Session 9 can run before it.
