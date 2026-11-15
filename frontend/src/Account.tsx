import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, BusinessSummary, Me, session } from "./api";
import { goTo } from "./App";
import { ErrorBox } from "./Describe";

/** The signed-in account (null while loading). The server decides what anyone may do; this is only for display. */
export function useMe(fresh = false): Me | null {
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    let live = true;
    session
      .me(fresh) // fresh: ask the server again (status may have changed, e.g. just approved)
      .then((m) => live && setMe(m))
      .catch(() => live && setMe({ user: null, guest: false, csrf: null, practice_server: true, limits: { shops: 3 } }));
    const off = session.onChange((m) => live && setMe(m));
    return () => {
      live = false;
      off();
    };
  }, [fresh]);
  return me;
}

/** `#/page?x=1` → URLSearchParams of the part after "?". */
export const hashParams = () => new URLSearchParams(window.location.hash.split("?")[1] ?? "");

const asError = (e: unknown) => (e instanceof ApiError ? e : new ApiError(String(e), 0));

// ---------- sign in → check your email ----------

export function SignInPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<{ message: string; dev_link?: string } | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const next = hashParams().get("next");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setSent(await api.requestLink(email.trim(), next ? `#/${next}` : undefined));
    } catch (err) {
      setError(asError(err));
    } finally {
      setBusy(false);
    }
  }

  if (sent)
    return (
      <>
        <p className="eyebrow">Sign in</p>
        <h1>Check your email</h1>
        <p className="tagline">{sent.message}</p>
        <p className="muted">Open the email on this phone or computer and tap “Sign in”. No password needed.</p>
        {sent.dev_link && (
          <section className="card" role="note">
            <p className="practice">Local development: the email isn't sent, here is the link.</p>
            <p>
              <a className="btn btn-ghost" href={sent.dev_link.slice(sent.dev_link.indexOf("#"))}>
                Open the sign-in link
              </a>
            </p>
          </section>
        )}
        <button className="btn btn-ghost btn-sm" onClick={() => setSent(null)}>
          Use a different email
        </button>
      </>
    );

  return (
    <>
      <p className="eyebrow">Sign in</p>
      <h1>Sign in to LaunchWitness</h1>
      <p className="tagline">We'll email you a link. Your shop's orders and warnings go to this address.</p>
      <form className="card" onSubmit={submit}>
        <label className="field">
          <span>Your email</span>
          <input
            type="email"
            required
            autoComplete="email"
            inputMode="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@gmail.com"
            maxLength={254}
          />
        </label>
        {error && <ErrorBox error={error} />}
        <button className="btn btn-primary" type="submit" disabled={busy || !email.trim()}>
          {busy ? "Sending…" : "Email me a link"}
        </button>
      </form>
      <p className="muted">
        Just looking? You can <a href="#/try">try it without signing in</a>. Practice shops are kept for a day.
      </p>
      <p className="muted">
        By signing in you agree to our <a href="#/terms">Terms of use</a>. Our <a href="#/privacy">Privacy page</a> says
        what we keep and how to delete it.
      </p>
    </>
  );
}

// ---------- the page the emailed link opens: a button, so opening the link uses nothing up ----------

export function ConfirmSignInPage() {
  const params = hashParams();
  const token = params.get("token") ?? "";
  const next = params.get("next");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const me = await api.confirm(token);
      const kept = me.kept_shops ? `?kept=${me.kept_shops}` : "";
      goTo(next ? `#/${next}` : `#/shops${kept}`);
    } catch (err) {
      setError(asError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className="eyebrow">Sign in</p>
      <h1>Sign in to LaunchWitness</h1>
      <p className="tagline">Tap the button to finish signing in on this device.</p>
      {error && <ErrorBox error={error} />}
      {error ? (
        <a className="btn btn-ghost" href="#/signin">
          Ask for a new link
        </a>
      ) : (
        <button className="btn btn-primary" disabled={busy || !token} onClick={confirm}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      )}
    </>
  );
}

// ---------- my shops ----------

function shopState(b: BusinessSummary): string {
  if (b.paused) return "Paused by our team";
  if (b.review === "held") return "Waiting for our team to look";
  if (b.public) return "Live";
  if (b.guest) return "Practice · kept for a day";
  return "Practice";
}

export function MyShopsPage() {
  const me = useMe(true);
  const [shops, setShops] = useState<BusinessSummary[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const kept = Number(hashParams().get("kept") ?? 0);

  useEffect(() => {
    api.list().then(setShops).catch(setError);
  }, []);

  if (error) return <ErrorBox error={error} />;
  if (!me || !shops) return <p>Loading…</p>;
  const user = me.user;
  return (
    <>
      <p className="eyebrow">{user ? user.email : "Practice"}</p>
      <h1>Your shops</h1>
      {kept > 0 && (
        <p className="status status-ok" role="status">
          We kept your practice shop{kept > 1 ? "s" : ""} in your account.
        </p>
      )}
      {user?.status === "pending" && <PendingNote />}
      {!user && <GuestNote />}
      {shops.length === 0 ? (
        <section className="card">
          <p>No shops yet.</p>
          <a className="btn btn-primary" href="#/try">
            Describe your business
          </a>
        </section>
      ) : (
        <ul className="names shops">
          {shops.map((b) => (
            <li key={b.id}>
              <span>
                <a href={`#/b/${b.id}`}>
                  <strong>{b.name}</strong>
                </a>
                <br />
                <span className="muted">{shopState(b)}</span>
              </span>
              <a className="btn btn-ghost btn-sm" href={`#/b/${b.id}/report`}>
                Report
              </a>
            </li>
          ))}
        </ul>
      )}
      {user && shops.length > 0 && shops.length < me.limits.shops && (
        <p>
          <a href="#/try">Make another shop</a> <span className="muted">(up to {me.limits.shops})</span>
        </p>
      )}
    </>
  );
}

export function PendingNote() {
  return (
    <p className="practice" role="note">
      You can practise now. We'll email you when you can launch for real.
    </p>
  );
}

export function GuestNote() {
  return (
    <p className="practice" role="note">
      Practice. <a href="#/signin">Sign in</a> to keep this shop.
    </p>
  );
}

// ---------- account: log out, log out everywhere, delete ----------

export function AccountPage() {
  const me = useMe(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [devLink, setDevLink] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(asError(err));
    } finally {
      setBusy(null);
    }
  };

  if (!me) return <p>Loading…</p>;
  if (!me.user)
    return (
      <>
        <h1>Your account</h1>
        <p>
          You're not signed in. <a href="#/signin">Sign in</a>
        </p>
      </>
    );
  const status = { pending: "Waiting for approval", approved: "Approved", suspended: "Suspended", deleted: "Deleted" };
  return (
    <>
      <p className="eyebrow">Account</p>
      <h1>{me.user.email}</h1>
      <p className="tagline">
        {status[me.user.status]}
        {me.user.role === "admin" ? " · team" : ""}
      </p>
      {me.user.status === "pending" && <PendingNote />}
      <section className="card">
        <h2>Sign out</h2>
        <div className="actions">
          <button
            className="btn btn-ghost"
            disabled={!!busy}
            onClick={() =>
              run("out", async () => {
                await api.logout();
                goTo("#/");
              })
            }
          >
            Log out
          </button>
          <button
            className="btn btn-ghost"
            disabled={!!busy}
            onClick={() =>
              run("all", async () => {
                await api.logoutAll();
                goTo("#/signin");
              })
            }
          >
            Log out on every device
          </button>
        </div>
      </section>
      <section className="card">
        <h2>Delete my account</h2>
        <p className="muted">
          Takes your shops off the internet and deletes them with their orders. We'll email you a link to confirm first.
        </p>
        {note ? (
          <p role="status">{note}</p>
        ) : (
          <button
            className="btn btn-ghost"
            disabled={!!busy}
            onClick={() =>
              run("del", async () => {
                const r = await api.deleteRequest();
                setNote(r.message);
                setDevLink(r.dev_link ?? null);
              })
            }
          >
            {busy === "del" ? "Sending…" : "Email me a link to delete my account"}
          </button>
        )}
        {devLink && (
          <p className="practice">
            Local development: <a href={devLink.slice(devLink.indexOf("#"))}>open the delete link</a>
          </p>
        )}
      </section>
      {error && <ErrorBox error={error} />}
    </>
  );
}

export function DeleteAccountPage() {
  const token = hashParams().get("token") ?? "";
  const me = useMe();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  if (!me) return <p>Loading…</p>;
  if (done)
    return (
      <>
        <h1>Your account is deleted</h1>
        <p>Your shops are off the internet and their orders are gone. Thank you for trying LaunchWitness.</p>
      </>
    );
  if (!me.user)
    return (
      <>
        <h1>Delete your account</h1>
        <p>
          Please <a href="#/signin">sign in</a> on this device first, then open the link from the email again.
        </p>
      </>
    );
  return (
    <>
      <h1>Delete your account?</h1>
      <p className="tagline">
        This takes your shops off the internet and deletes them with their orders. It can't be undone.
      </p>
      {error && <ErrorBox error={error} />}
      <div className="actions">
        <button
          className="btn btn-primary"
          disabled={busy || !token}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await api.deleteAccount(token);
              setDone(true);
            } catch (err) {
              setError(asError(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Deleting…" : "Yes, delete everything"}
        </button>
        <a className="btn btn-ghost" href="#/account">
          Keep my account
        </a>
      </div>
    </>
  );
}
