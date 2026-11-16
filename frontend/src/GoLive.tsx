import { useEffect, useState } from "react";
import { api, ApiError, GoLive } from "./api";

/** Shown when the owner opens the preview, so the checklist ticks "looked at your preview" straight away. */
export const PREVIEWED_EVENT = "lw:previewed";

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

/**
 * The go-live checklist (S10.5). Drafts and practice never need it; only "Launch for real" does, and the server
 * enforces it. The owner's own checks are stored as "confirmed by you", never as "verified".
 * `version` changes after each save so the list is fetched again.
 */
export function GoLiveCard({ businessId, version }: { businessId: number; version: number }) {
  const [g, setG] = useState<GoLive | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [waTried, setWaTried] = useState(false);
  const [showUpi, setShowUpi] = useState(false);
  const [ownGoods, setOwnGoods] = useState(false);
  const [terms, setTerms] = useState(false);

  useEffect(() => {
    const load = () => api.golive(businessId).then(setG).catch(() => setG(null));
    load();
    window.addEventListener(PREVIEWED_EVENT, load);
    return () => window.removeEventListener(PREVIEWED_EVENT, load);
  }, [businessId, version]);

  if (!g) return null;
  const run = async (label: string, fn: () => Promise<GoLive>) => {
    setBusy(label);
    setError("");
    try {
      setG(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That didn't work. Please try again.");
    } finally {
      setBusy(null);
    }
  };
  const done = g.items.filter((i) => i.done).length;
  const item = (key: string) => g.items.find((i) => i.key === key);

  return (
    <section className="card golive" aria-labelledby="golive-h">
      <h2 id="golive-h">Before you go live</h2>
      <p className="muted">
        {g.ready
          ? "Everything is ready for a real launch."
          : `${done} of ${g.items.length} done. You can keep practising without these; a real launch needs all of them.`}
      </p>
      <ul className="golive-list">
        {g.items.map((i) => (
          <li key={i.key} className={i.done ? "ok" : "todo"}>
            <span className="mark" aria-hidden>
              {i.done ? "✓" : "○"}
            </span>
            <span>
              {i.label}
              <span className="sr-only">{i.done ? " (done)" : " (still to do)"}</span>
              {!i.done && i.hint && <small className="muted"> {i.hint}</small>}
            </span>
          </li>
        ))}
      </ul>

      {g.whatsapp_test_url && !g.confirmed.whatsapp_at && (
        <div className="golive-step">
          <h3>Check your WhatsApp number</h3>
          <p className="muted">
            Customers use <strong>{g.whatsapp}</strong> to reach you. Tap “Test this number”: it should open a chat with
            yourself. If it opens someone else, fix the number above and save.
          </p>
          <div className="actions">
            <a className="btn btn-wa btn-sm" href={g.whatsapp_test_url} target="_blank" rel="noopener noreferrer" onClick={() => setWaTried(true)}>
              Test this number
            </a>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!waTried || busy !== null}
              onClick={() => run("wa", () => api.confirmCheck(businessId, "whatsapp"))}
            >
              Yes, that's me
            </button>
          </div>
        </div>
      )}
      {g.confirmed.whatsapp_at && (
        <p className="confirmed">WhatsApp number confirmed by you on {when(g.confirmed.whatsapp_at)}.</p>
      )}

      {g.upi_test && item("upi") && !g.confirmed.upi_at && (
        <div className="golive-step">
          <h3>The ₹1 UPI test</h3>
          {g.upi_test.name ? (
            <>
              <p className="muted">
                Scan this with <strong>your own phone</strong>. Your UPI app should show <strong>{g.upi_test.name}</strong>.
                You don't have to pay: you can stop at the PIN screen once you've seen the name. We never touch money.
                (Some UPI apps won't let you pay your own ID; seeing the name is enough.)
              </p>
              {showUpi ? (
                <div className="upi-test">
                  <div className="upi-qr" dangerouslySetInnerHTML={{ __html: g.upi_test.qr_svg }} />
                  <a className="btn btn-ghost btn-sm" href={g.upi_test.uri}>
                    Open my UPI app (on this phone)
                  </a>
                </div>
              ) : (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowUpi(true)}>
                  Show my ₹1 UPI test
                </button>
              )}
              <div className="actions">
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={!showUpi || busy !== null}
                  onClick={() => run("upi", () => api.confirmCheck(businessId, "upi"))}
                >
                  Yes, my UPI app showed “{g.upi_test.name}”
                </button>
              </div>
            </>
          ) : (
            <p className="muted">Add the name your UPI app shows (above) and save, then do the test.</p>
          )}
        </div>
      )}
      {g.confirmed.upi_at && <p className="confirmed">UPI name test confirmed by you on {when(g.confirmed.upi_at)}.</p>}

      {!(g.confirmed.own_goods_at && g.confirmed.terms_at) ? (
        <div className="golive-step">
          <h3>Two promises</h3>
          <label className="check">
            <input type="checkbox" checked={ownGoods} onChange={(e) => setOwnGoods(e.target.checked)} />
            <span>I make or sell these myself, and I'm allowed to sell them.</span>
          </label>
          <label className="check">
            <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} />
            <span>
              I accept the{" "}
              <a href="#/terms" target="_blank" rel="noopener">
                Terms
              </a>
              .
            </span>
          </label>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!ownGoods || !terms || busy !== null}
            onClick={() => run("agree", () => api.confirmCheck(businessId, "agreements", { own_goods: true, terms: true }))}
          >
            Save my answers
          </button>
        </div>
      ) : (
        <p className="confirmed">Promises saved on {when(g.confirmed.terms_at)}.</p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p className="muted small">
        We never ask for Aadhaar, PAN, bank account or card numbers, passwords, your date of birth or your home address.
      </p>
    </section>
  );
}
