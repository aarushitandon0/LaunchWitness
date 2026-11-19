import { useState } from "react";
import { api, ApiError, Business } from "./api";

/** S21: "Sold out today" for each item, one tap each. It changes no words, so it is saved at once (no policy check),
 * even on a live shop. The server names the item by its place AND its name; a menu changed elsewhere answers 409.
 * `compact` folds the list into a <details> (My shops card). */
export function SoldOutToday({
  biz,
  onChange,
  compact = false,
}: {
  biz: Business;
  onChange: (b: Business) => void;
  compact?: boolean;
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  const items = biz.profile.products.map((p, i) => ({ p, i })).filter(({ p }) => !p.addon && p.name.trim());
  if (!items.length) return null;
  const out = items.filter(({ p }) => p.sold_out).length;

  const flip = async (i: number, name: string, now: boolean) => {
    setBusy(i);
    setError("");
    try {
      onChange(await api.setSoldOut(biz.id, i, name, now));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That didn't work. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  const list = (
    <>
      <ul className="soldout-list">
        {items.map(({ p, i }) => (
          <li key={i}>
            <span>{p.name}</span>
            <button
              type="button"
              className={`btn btn-sm ${p.sold_out ? "btn-primary" : "btn-ghost"}`}
              aria-pressed={!!p.sold_out}
              aria-label={`${p.name}: sold out today`}
              disabled={busy !== null}
              onClick={() => flip(i, p.name, !p.sold_out)}
            >
              {busy === i ? "Saving…" : p.sold_out ? "Sold out today" : "On sale"}
            </button>
          </li>
        ))}
      </ul>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <p className="muted small">Customers see “Sold out today” and can't order it. Tap again when it's back.</p>
    </>
  );

  if (compact)
    return (
      <details className="soldout soldout-compact">
        <summary>
          Sold out today{out ? ` (${out})` : ""}
        </summary>
        {list}
      </details>
    );
  return (
    <section className="card soldout">
      <h2>Sold out today</h2>
      {list}
    </section>
  );
}
