# LaunchWitness: from business idea to customer-ready

*GoDaddy Inclusive Innovation Hackathon 2026 · Round 2 · Open Innovation*

> **A real order reaches you, proven.** LaunchWitness puts a home seller's shop online on GoDaddy, places a real test
> order through the shop's own form, and shows her it arrived in her inbox before her first customer does. It fixes
> what breaks and keeps checking.

Live: https://launchwitness.com · A real launched shop: https://meeras-eggless-bakes.launchwitness.com ·
Its proof report: https://launchwitness.com/r/GsZj7gOAoCydSauqdNpoaWksKHVW-HSz · Build replay: https://launchwitness.com/build

## The problem

Home sellers in India (cakes, tiffins, tailoring, crafts, gift hampers) take orders in Instagram and WhatsApp
messages. A website could bring them customers, but setting one up is technical, and nobody checks it end to end.
A missing email setting sends orders to spam; an address stops pointing at the shop. There is no error message. The
seller just gets fewer orders. Her first sale becomes her first problem.

## The user

**Meera** bakes eggless cakes at home in Pune. She has a phone, a price list and customers who message her. She does
not know what DNS is. She needs one answer: if a customer orders, will I get it?

## The solution

1. **Describe.** She types a few lines and pastes her price list, or photographs it. Claude reads it into a shop.
2. **Review.** She checks it as an ordinary form with a private preview, adds photos, picks one of six looks.
3. **Launch on GoDaddy.** One approval card shows every change and the cost. Code backs up DNS, writes the shop's
   record through the GoDaddy API, and HTTPS is issued for the shop.
4. **Prove.** The checker places a real test order through her public order form and follows it: form accepted →
   mail server accepted → found in the inbox over IMAP (or she taps "Yes, I got it"). It also checks the address
   (asking GoDaddy's own nameservers), HTTPS and the email settings. Only when every check passes does the report say
   "ready for customers". Every claim is stored as evidence in a tamper-evident hash chain that anyone with the link
   can re-verify.
5. **Fix and keep watching.** A failed check is explained in one plain sentence and repaired from five fixes written
   in code, then checked again. After launch: the site every 15 minutes, settings and expiry dates daily.

Around the proof, the shop does what her customers need: a menu in ₹ with sizes, pickup or delivery, a date picker
that knows her notice and days off, UPI payment shown only after an order (with "Customer says paid" for her to check),
custom requests with a reference photo for photo cakes and tailoring, and an Orders page.

## Demo flow (about three minutes)

1. Landing page → **Try it without an account** → pick Meera → her shop appears on Review.
2. Run a practice launch: watch each step and each check; open the report.
3. Open the real launched shop and its shared report; press **Verify** to recompute the evidence chain.
4. Place an order on the shop; it appears on the Orders page and in the email.
5. Use the demo fault switch: a check fails, the Doctor explains it in one sentence, applies a playbook fix, and the
   check turns green again.

## How Claude is used

Claude **decides and explains**; plain code **acts and checks**. The Reader (strong model) turns her words into a
validated shop profile. The Namer suggests names; code checks availability and price. The Doctor investigates a
failed check with read-only tools and picks a fix id from a fixed playbook, or says "needs you". The policy check can
only hold a shop for a human. Claude never spends money and never writes DNS. Calls are capped by `max_tokens` and a
daily budget; if Claude is unavailable, plain rules take over and the policy check fails closed.

## How GoDaddy is used

GoDaddy is load-bearing. The domain `launchwitness.com`; the **DNS API** for each shop's record, always backed up
first and limited to the app's own domains; **GoDaddy's authoritative nameservers** as the source of truth for the
address check; one **GoDaddy VPS** running Docker (Caddy for HTTPS, the FastAPI app); and a **GoDaddy Professional
Email** mailbox that sends every email over SMTP and is read over IMAP to prove the test order arrived.

## Impact

A home seller gets a shop she can share with confidence, because she has seen proof that an order reaches her, and
she hears about a problem before her customers do. She keeps taking payments by UPI as she does today, and she never
has to learn what an MX record is. Practice mode lets anyone try the full flow without an account or any spending.

## What's next

- Launches on the seller's own domain and a mailbox per seller, through the guarded purchase path and GoDaddy's email API.
- Running on the seller's own GoDaddy account, so she owns everything.
- "Was this you?" when a setting changes, instead of a silent fix.
- Bookings for salons and tutors, and more Indian languages for the description.
- Card payments through a gateway once a seller has done KYC.
