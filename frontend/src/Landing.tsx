import { FormEvent, useState } from "react";
import { api, ApiError } from "./api";
import { ErrorBox } from "./Describe";

const STEPS = [
  ["Describe", "Write a few lines about your business and paste your price list, the way you'd tell a friend."],
  ["Check", "We turn it into your website. You fix anything we got wrong, then pick a free address or your own name."],
  ["Approve", "You see every step, every setting we'll change and the exact cost. Nothing happens until you say yes."],
  ["Proof", "We launch it, then prove it works: the site opens securely, email is set up, and a test order reaches your inbox."],
];

const PROMISES = [
  ["Nothing is bought without your approval", "You see the exact price first. Buying is switched off unless you approve it."],
  ["You see every change before it happens", "Each setting is shown as before and after, in plain words."],
  ["A backup first, and an undo", "We save a copy of your settings before changing anything, so a failed launch can be put back."],
];

export default function Landing() {
  return (
    <>
      <section className="hero">
        <h1>Describe your business. We put it online on GoDaddy, and prove it works.</h1>
        <p className="tagline">
          Meera bakes eggless cakes in Pune. Her customers find her on Instagram and order in messages, but she has no
          website, no business email, and no time to learn what “DNS” means. LaunchWitness turns her two lines and a
          price list into a live shop with her own name and email, and checks that a real order reaches her inbox
          before her first customer does.
        </p>
        <div className="actions">
          <a className="btn btn-primary" href="#/try">
            Try it (practice mode)
          </a>
          <a className="btn btn-ghost" href="/build">
            How this was built
          </a>
        </div>
        <p className="muted small">Practice mode uses a pretend GoDaddy: nothing is bought and no real settings change.</p>
      </section>

      <h2>How it works</h2>
      <ol className="card how">
        {STEPS.map(([title, text], i) => (
          <li key={title}>
            <span className="num" aria-hidden>
              {i + 1}
            </span>
            <div>
              <div className="title">{title}</div>
              <div>{text}</div>
            </div>
          </li>
        ))}
      </ol>

      <h2>Our promises</h2>
      <ul className="card promises">
        {PROMISES.map(([title, text]) => (
          <li key={title}>
            <div className="title">✅ {title}</div>
            <div className="muted">{text}</div>
          </li>
        ))}
      </ul>

      <h2>Contact us</h2>
      <ContactForm />
    </>
  );
}

function ContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.contact(name, email, message, website);
      setSent(r.message);
      setMessage("");
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(String(err), 0));
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div className="status status-ok" role="status">
        <p>{sent}</p>
      </div>
    );
  }
  return (
    <form className="card" onSubmit={submit}>
      <label className="field">
        <span>Your name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} autoComplete="name" />
      </label>
      <label className="field">
        <span>Your email</span>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} autoComplete="email" />
        <small>So we can reply. We don't add you to any list.</small>
      </label>
      <label className="field">
        <span>Message</span>
        <textarea rows={4} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={3000} />
      </label>
      <label className="hp" aria-hidden>
        Leave this empty
        <input tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
      </label>
      {error && <ErrorBox error={error} />}
      <button className="btn btn-primary" type="submit" disabled={busy || !name.trim() || !email.trim() || !message.trim()}>
        {busy ? "Sending…" : "Send message"}
      </button>
    </form>
  );
}
