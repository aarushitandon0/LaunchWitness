import { Product } from "./api";

/** S21: how one item is sold, on the Review page. Everything here is optional; the server checks every field again
 * (labels and choices are plain text, prices above 0, at most 8 sizes and 8 choices) and draws it on the shop. */
const KINDS: [NonNullable<Product["option_kind"]>, string][] = [
  ["", "Sizes"],
  ["size", "Size"],
  ["weight", "Weight"],
  ["pack", "Pack"],
  ["count", "How many"],
  ["other", "Something else"],
];
const UNITS: [NonNullable<Product["unit"]>, string][] = [
  ["", "Nothing to add"],
  ["piece", "per piece"],
  ["box", "per box"],
  ["kg", "per kg"],
  ["g", "per gram"],
  ["dozen", "per dozen"],
  ["set", "per set"],
  ["bunch", "per bunch"],
  ["metre", "per metre"],
];
const MAX = 8;
const lowest = (options: { price_inr: number }[]) => {
  const prices = options.map((o) => o.price_inr).filter((x) => x > 0);
  return prices.length ? Math.min(...prices) : 0;
};
const whole = (v: string, lo: number, hi: number) => Math.min(hi, Math.max(lo, Math.round(Number(v) || 0)));

export function ItemSelling({ p, n, onChange }: { p: Product; n: number; onChange: (patch: Partial<Product>) => void }) {
  const options = p.options ?? [];
  const choices = p.choices ?? [];
  const extras = [options.length && `${options.length} size${options.length === 1 ? "" : "s"}`,
    (p.min_qty ?? 1) > 1 && `min ${p.min_qty}`, choices.length && `${choices.length} choices`,
    (p.notice_days ?? 0) > 0 && `${p.notice_days} days' notice`, p.unit && "unit"].filter(Boolean);
  const setOption = (j: number, patch: Partial<{ label: string; price_inr: number }>) =>
    onChange({ options: options.map((o, k) => (k === j ? { ...o, ...patch } : o)) });
  const setChoice = (j: number, value: string) => onChange({ choices: choices.map((c, k) => (k === j ? value : c)) });

  return (
    <details className="sell-how">
      <summary>
        Sizes, minimum, choices{extras.length ? <span className="muted"> · {extras.join(", ")}</span> : null}
      </summary>
      <fieldset className="sell-group">
        <legend>Sizes or packs, each with its own price</legend>
        {options.map((o, j) => (
          <div className="sell-row" key={j}>
            <label className="field grow">
              <span>Size {j + 1}</span>
              <input
                aria-label={`Item ${n} size ${j + 1}`}
                value={o.label}
                maxLength={40}
                placeholder="e.g. ½ kg"
                onChange={(e) => setOption(j, { label: e.target.value })}
              />
            </label>
            <label className="field price">
              <span>Price (₹)</span>
              <input
                aria-label={`Item ${n} size ${j + 1} price`}
                type="number"
                inputMode="numeric"
                min={1}
                value={o.price_inr}
                onChange={(e) => setOption(j, { price_inr: whole(e.target.value, 0, 10_000_000) })}
              />
            </label>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              aria-label={`Remove size ${j + 1}`}
              onClick={() => onChange({ options: options.filter((_, k) => k !== j) })}
            >
              Remove
            </button>
          </div>
        ))}
        {options.length < MAX && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => onChange({ options: [...options, { label: "", price_inr: options.length ? 0 : p.price_inr }] })}
          >
            + Add a size
          </button>
        )}
        {options.length > 0 && (
          <label className="field">
            <span>Customers see them as</span>
            <select value={p.option_kind ?? ""} onChange={(e) => onChange({ option_kind: e.target.value as Product["option_kind"] })}>
              {KINDS.map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
            <small>Your shop shows “from ₹{lowest(options)}” and a box for each size.</small>
          </label>
        )}
      </fieldset>
      <div className="sell-row">
        <label className="field">
          <span>Price is</span>
          <select value={p.unit ?? ""} onChange={(e) => onChange({ unit: e.target.value as Product["unit"] })}>
            {UNITS.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field price">
          <span>Minimum order</span>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={100}
            value={p.min_qty ?? 1}
            onChange={(e) => onChange({ min_qty: whole(e.target.value, 1, 100) })}
          />
        </label>
        <label className="field price">
          <span>Maximum (0 = no limit)</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={100}
            value={p.max_qty ?? 0}
            onChange={(e) => onChange({ max_qty: whole(e.target.value, 0, 100) })}
          />
        </label>
        <label className="field price">
          <span>Days' notice for this item</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={30}
            value={p.notice_days ?? 0}
            onChange={(e) => onChange({ notice_days: whole(e.target.value, 0, 30) })}
          />
        </label>
      </div>
      <fieldset className="sell-group">
        <legend>One choice customers must make (same price)</legend>
        <label className="field">
          <span>What they choose</span>
          <input
            value={p.choice_label ?? ""}
            maxLength={30}
            placeholder="e.g. Flavour or Colour"
            onChange={(e) => onChange({ choice_label: e.target.value })}
          />
        </label>
        {choices.map((c, j) => (
          <div className="sell-row" key={j}>
            <label className="field grow">
              <span>Choice {j + 1}</span>
              <input aria-label={`Item ${n} choice ${j + 1}`} value={c} maxLength={30} onChange={(e) => setChoice(j, e.target.value)} />
            </label>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              aria-label={`Remove choice ${j + 1}`}
              onClick={() => onChange({ choices: choices.filter((_, k) => k !== j) })}
            >
              Remove
            </button>
          </div>
        ))}
        {choices.length < MAX && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange({ choices: [...choices, ""] })}>
            + Add a choice
          </button>
        )}
      </fieldset>
      <label className="check">
        <input
          type="checkbox"
          data-testid="custom-toggle"
          checked={!!p.custom}
          onChange={(e) => onChange({ custom: e.target.checked })}
        />
        <span>Takes custom requests (the order form asks what they want and allows one reference photo)</span>
      </label>
      <label className="check">
        <input type="checkbox" checked={!!p.sold_out} onChange={(e) => onChange({ sold_out: e.target.checked })} />
        <span>Sold out today (customers can't order it until you untick this)</span>
      </label>
    </details>
  );
}
