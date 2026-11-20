# LaunchWitness: short answers for judges

**Isn't this just a website builder, or GoDaddy Airo?**
No. Building the shop is step one of five, and the least new one. What LaunchWitness adds is the part no builder
does: after the shop goes live, it places a real test order through the shop's own public order form and follows it
until it is found in the inbox (or the seller taps "Yes, I got it"). It checks the address, HTTPS and email settings,
repairs what fails from a fixed playbook, and keeps checking after launch. The report only says "ready for customers"
when every check has passed, and each claim is backed by stored, tamper-evident evidence.

**How does the seller know a customer paid?**
She checks her own UPI app. After a real order the customer sees a UPI link and QR code for the exact amount, with
the order reference as the payment note. After paying, the customer can enter the 12-digit UPI reference (and an
optional screenshot). The seller's Orders page then shows **"Customer says paid"**, never "Paid". She marks the order
Paid herself once she sees the money. LaunchWitness never sees a bank and never claims a payment happened.

**Why no payment gateway?**
A gateway needs the seller's KYC, a business bank account and fees, which is a real barrier for a home seller who
already gets paid by UPI every day. UPI links move money straight from the customer to the seller; nothing passes
through LaunchWitness. Card payments through a gateway are listed as future work.

**Why hide the UPI ID on the shop page?**
A UPI ID on a public page can be copied onto a fake shop, and it invites payments with no order behind them. So the
shop page says how payment works but shows no ID or QR. The UPI details appear only after a real order, on the
thank-you page and the order's own unguessable status page, with the exact amount and the order reference.

**What if Claude is wrong, or someone hides instructions in their shop description?**
Claude never acts. It returns data (a profile, names, a finding, a fix id, OK or hold), and code validates every
field. The Doctor can only pick from five fixes written in code; anything else is refused and logged. The seller's
text and every tool result are passed to Claude as data, and a prompt-injection seller is part of the test suite.
The Reader's output is shown to the seller on Review before anything goes live. The policy check can only hold a shop
for a human; it can never launch one.

**What if the Claude API is down or over budget?**
Every call has a tight `max_tokens` and there is a daily spend cap. When Claude can't answer: the policy check fails
closed (the shop is held for the team, not launched), the Doctor falls back to plain rules (a single allowed standard
fix, or clear instructions for the owner), and the Reader shows a plain message asking the seller to try again.
Checks, repairs and monitoring are plain code and keep working.

**What does it cost to run?**
One GoDaddy VPS, the `launchwitness.com` domain and one GoDaddy Professional Email mailbox, all from hackathon credit;
real shops use free subdomains, so no domain is bought per seller. Claude is a few calls per launch: the Reader
(strong model) once, the Namer and the policy check (cheap model) once each, and the Doctor only when a check fails.
The live Claude spend is capped per day in configuration.

**How do custom orders work?**
An item can be marked "Takes custom requests" (photo cakes, theme cakes, tailoring, custom gifts). The Reader sets
it only when the seller's own words say so, and she can switch it on Review. When a customer orders such an item, the
form asks "Tell us what you want" for it (up to 500 characters: the message on the cake, the design, measurements)
and allows one reference photo (JPG, PNG or WebP, up to 5 MB). The photo is re-drawn from its pixels (no location or
camera data), is visible only to the seller on her Orders page, is never attached to an email or given a public
link, and is deleted 30 days after the order is done or cancelled.

**Isn't it one template?**
Yes, on purpose: one rendering engine and one template, server-rendered. That is what makes every shop testable and
safe (strict CSP, escaping tested in every look, the checker's marker on every page). Within it there are six looks
for home businesses (bakery, home kitchen, handmade, tailoring, gifts, general), each with accent colours, its own
fonts and a per-shop drawn signature, plus the seller's own photos. Claude picks keys; code draws everything.
