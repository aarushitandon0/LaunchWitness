# HackerEarth submission: values to paste

## Title

LaunchWitness: from business idea to customer-ready, proven on GoDaddy

## Theme

Open Innovation

## Demo link

https://launchwitness.com

## Repository URL

https://github.com/aarushitandon0/LaunchWitness

> Note for the owner: this repository is private today (it answers 404 when signed out). Make it public, or add the
> judges as collaborators, before submitting; otherwise rely on the Source Code zip.

## Files

- **Source Code:** `dist/LaunchWitness-source.zip` (a `git archive` of the final `main` commit: tracked files only)
- **Additional File:** `dist/LaunchWitness-brief.pdf` (the project brief)

## Description (Markdown)

**From business idea to customer-ready. Be ready before your first customer arrives.**

Home sellers in India (cakes, tiffins, tailoring, gift hampers) take orders over Instagram and WhatsApp. When they do
get a website, nobody checks it works end to end: a missing email setting sends orders to spam, an address stops
pointing at the shop, and the seller just sees fewer orders.

**LaunchWitness** builds a seller's shop from a few lines and her price list, launches it on GoDaddy, and then
**proves a real order reaches her**: it places a test order through the shop's own public form and follows it until
it is found in the inbox. It also checks the address (on GoDaddy's own nameservers), HTTPS and email settings, fixes
what fails from a fixed playbook of safe repairs, and keeps checking after launch. The report says "ready for
customers" only when every check passed, and every claim sits in a tamper-evident evidence chain anyone can
re-verify.

**Claude decides and explains; plain code acts.** Claude reads her messy menu (Reader), suggests names (Namer),
explains a failed check and picks a fix from the playbook (Doctor), and can hold a shop for review (policy check). It
never spends money or writes DNS: code does, with backups, spend guards and an audit row for every change.

**GoDaddy is load-bearing:** the domain, DNS writes through the GoDaddy API (backed up first), a GoDaddy VPS running
Docker with automatic HTTPS, and a GoDaddy Professional Email mailbox for SMTP sending and IMAP proof.

For customers: prices in ₹ with sizes, pickup or delivery, UPI shown only after an order ("Customer says paid" for the
seller to check), and custom requests with a reference photo for photo cakes and tailoring.

**Links**
- App: https://launchwitness.com
- A real launched shop: https://meeras-eggless-bakes.launchwitness.com
- Its proof report: https://launchwitness.com/r/GsZj7gOAoCydSauqdNpoaWksKHVW-HSz (add `/verify` to recompute the chain)
- How it was built with Claude Code: https://launchwitness.com/build

**Try it with no account:** open the app → **Try it without an account** → pick an example seller → run a practice
launch (everything runs against a pretend GoDaddy; nothing is bought). Or open a demo shop, e.g.
https://launchwitness.com/demo/meera.
