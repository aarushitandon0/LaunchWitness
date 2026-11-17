/** The app's own Privacy page and Terms of use. Plain English, v1 (beta). Not legal advice. */

const CONTACT = "hello@launchwitness.com";
const UPDATED = "16 November 2026";

function Meta() {
  return (
    <p className="muted">
      Version 1 (beta) · updated {UPDATED} · questions: <a href={`mailto:${CONTACT}`}>{CONTACT}</a>
    </p>
  );
}

export function PrivacyPage() {
  return (
    <article className="legal">
      <p className="eyebrow">Privacy</p>
      <h1>What we keep about you, and why</h1>
      <Meta />
      <p>
        LaunchWitness is a small beta service. This page lists everything we store, in plain words. It is not legal
        advice, and we'll update it as the service changes.
      </p>

      <h2>What we store</h2>
      <ul>
        <li>
          <strong>Your email address</strong>: to sign you in (we email you a link; there are no passwords) and to send
          you your shop's orders and warnings.
        </li>
        <li>
          <strong>Your shop</strong>: what you typed or photographed (description, price list), the website made from it,
          its address, and the checks we run on it (what we saw, and when).
        </li>
        <li>
          <strong>Your customers' orders</strong>: the name and phone number a customer types, what they ordered, their
          note, the date they want it and, for delivery or shipping, their delivery address and PIN code. These are kept so
          you can see and export your orders. A customer's address is shown only to the shop owner (on the Orders page and
          in the order email). It is never shown on the shop's website, the shared report, the proof records or the audit
          log, and it is deleted when the shop or the account is deleted. We never ask for Aadhaar, PAN or bank details.
        </li>
        <li>
          <strong>Records of what happened</strong> (an audit log): sign-ins, launches, changes and checks, with the time.
          We keep these to find mistakes and abuse.
        </li>
        <li>
          <strong>For limits and safety only</strong>: a one-way scrambled form of your internet address (never the
          address itself) and your browser's name, so we can stop one person from using up everyone's limits.
        </li>
      </ul>
      <p>We don't sell any of it, we don't show ads, and we don't use tracking or advertising cookies.</p>

      <h2>Cookies</h2>
      <p>
        Two cookies, both only for this site: one keeps you signed in (14 days), and one keeps a practice shop you made
        without signing in (1 day). Shop pages never receive them.
      </p>

      <h2>Who else sees some of it</h2>
      <ul>
        <li>
          <strong>Anthropic (Claude)</strong> reads your description and price list (or photo) to write your website, and
          checks a new shop against our rules before it goes live.
        </li>
        <li>
          <strong>GoDaddy</strong> hosts our server, our email and the address records of live shops.
        </li>
        <li>
          <strong>Let's Encrypt</strong> issues each live shop's security certificate. Certificates are recorded in
          public logs, so <strong>a live shop's address becomes public</strong>.
        </li>
      </ul>

      <h2>How long we keep it</h2>
      <ul>
        <li>A practice shop made without signing in: deleted after 24 hours.</li>
        <li>Your shops and their orders: until you delete the shop or your account.</li>
        <li>Sign-in links work once, for 15 minutes; only a scrambled form of them is stored.</li>
        <li>
          Backups of the database are kept for up to 4 weeks, then overwritten. Something you delete can stay in a backup
          until then.
        </li>
      </ul>

      <h2>Deleting everything</h2>
      <p>
        Go to <a href="#/account">Your account</a> → <strong>Delete my account</strong>. We email you a link to confirm.
        That takes your shops off the internet and deletes them with their orders and records, erases your email, and
        signs you out everywhere. What stays: one line saying an account was deleted, and the records of your past
        sign-ins, which no longer carry your email. You can also delete a single shop on its page, or write to us.
      </p>
    </article>
  );
}

export function TermsPage() {
  return (
    <article className="legal">
      <p className="eyebrow">Terms of use</p>
      <h1>The deal, in plain words</h1>
      <Meta />
      <p>
        By using LaunchWitness you agree to these terms. They're written simply on purpose. They're not legal advice.
      </p>

      <h2>What LaunchWitness does</h2>
      <p>
        It builds a simple website for your home business from what you describe, puts it at an address under
        launchwitness.com, checks that a test order really reaches you, and keeps checking. It's a <strong>beta</strong>:
        things can break, and we may change or stop the service. We'll tell you by email before we stop it.
      </p>

      <h2>Your part</h2>
      <ul>
        <li>Only describe a business that is yours, and only sell things that are legal where you are.</li>
        <li>
          No medicines, weapons, adult content, gambling, alcohol or tobacco, no copies of other brands, and nothing that
          misleads customers. Our team may pause or remove a shop that breaks this, and tell you why.
        </li>
        <li>Check your website's details and prices. You're responsible for your products, prices and orders.</li>
        <li>Keep your email account safe: whoever can read it can sign in as you.</li>
      </ul>

      <h2>Money</h2>
      <p>
        LaunchWitness takes no payments and never buys anything for you automatically. Customers pay you directly. If
        something needs money (like renewing a website name), we tell you, and you decide.
      </p>

      <h2>Our part, and its limits</h2>
      <p>
        We work to keep your shop online and to tell you when something breaks. We can't promise it will always be up,
        or that every order will arrive. Please don't rely on it as your only way to take orders yet. As far as the law
        allows, we aren't responsible for lost orders or lost sales.
      </p>

      <h2>Ending</h2>
      <p>
        You can delete your account at any time (<a href="#/account">Your account</a>). We may suspend an account that
        breaks these terms or puts others at risk. See the <a href="#/privacy">Privacy page</a> for what happens to your
        data.
      </p>
    </article>
  );
}

export function LegalLinks() {
  return (
    <span className="legal-links">
      <a href="#/privacy">Privacy</a> · <a href="#/terms">Terms</a> · <a href="/build">How this was built</a>
    </span>
  );
}
