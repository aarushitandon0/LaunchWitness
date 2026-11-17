import { FormEvent, useEffect, useState } from "react";
import { ShopLink } from "./ShopLink";
import { ItemPhoto, ShopPhotos, usePhotos } from "./Photos";
import { api, ApiError, Business, Order, Product, Profile } from "./api";
import { ErrorBox } from "./Describe";
import { takeNote } from "./Report";
import { StepHeader } from "./Steps";
import { GoLiveCard } from "./GoLive";
import { ThemePicker } from "./ThemePicker";

type TextKey = {
  [K in keyof Profile]: Profile[K] extends string
    ? K extends
        | "kind"
        | "not_supported_reason"
        | "niche"
        | "delivery_areas"
        | "theme"
        | "accent"
        | "selling_mode"
        | "payment_terms"
        | "cancellation_preset"
        | "cancellation_text"
        | "shipping_note"
        | "back_on"
        | "allergens"
      ? never
      : K
    : never;
}[keyof Profile];

const FIELDS: { key: TextKey; label: string; hint?: string; long?: boolean }[] = [
  { key: "name", label: "Business name" },
  { key: "tagline", label: "One line about you", hint: "Shown at the top of your site." },
  { key: "about", label: "About", long: true },
  {
    key: "area",
    label: "Area or locality",
    hint: "Your neighbourhood, e.g. Baner. Only this and your city are shown, never your home address: you share the exact pickup address yourself on WhatsApp after you confirm an order.",
  },
  { key: "city", label: "City", hint: "e.g. Pune. Shown with your area." },
  { key: "hours", label: "Working days and hours", hint: "e.g. Tue–Sun, 10am–7pm. Closed Mondays." },
  { key: "phone", label: "Phone number" },
  { key: "whatsapp", label: "WhatsApp number", hint: "An Indian mobile number. Customers use it to reach you: your shop shows a WhatsApp button, and after ordering they can send you the order there." },
  { key: "instagram", label: "Instagram (optional)", hint: "Just your handle, e.g. @meera.bakes. Shown as a link on your shop." },
  { key: "upi_id", label: "UPI ID", hint: "e.g. yourname@okaxis — we show a QR code customers can scan to pay." },
  {
    key: "upi_display_name",
    label: "Name your UPI app shows",
    hint: "Customers see “Your UPI app should show: …” so they know they're paying the right person.",
  },
  {
    key: "fssai_number",
    label: "Food licence (FSSAI) number (optional)",
    hint: "14 digits. Home food businesses in India generally need FSSAI registration. We only show the number on your site; we don't check it.",
  },
];

const emptyProduct = (category: string): Product => ({
  name: "",
  price_inr: 0,
  description: "",
  category,
  addon: false,
  price_from: false,
  food_mark: "",
});

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const CANCEL_PRESETS: [string, string][] = [
  ["", "Don't say anything"],
  ["no_custom", "No cancellations for custom orders"],
  ["full_24h", "Cancel up to 24 hours before for a full refund"],
  ["advance_kept_48h", "Cancel up to 48 hours before; the advance is not refunded"],
  ["custom", "I'll write my own line"],
];

type Mode = Profile["selling_mode"];
const modeParts = (m: Mode): { pickup: boolean; kind: "none" | "local" | "india" } => ({
  pickup: m.startsWith("pickup"),
  kind: m.endsWith("local") ? "local" : m.endsWith("india") ? "india" : "none",
});
const toMode = (pickup: boolean, kind: "none" | "local" | "india"): Mode =>
  kind === "none" ? (pickup ? "pickup" : "") : (`${pickup ? "pickup_" : ""}${kind}` as Mode);

export default function Review({ id }: { id: number }) {
  const [biz, setBiz] = useState<Business | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [subdomain, setSubdomain] = useState("");
  const [orders, setOrders] = useState<Order[]>([]);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [saveError, setSaveError] = useState<ApiError | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [dirty, setDirty] = useState(false);
  const [slotsText, setSlotsText] = useState<string | null>(null);
  const [note] = useState(() => takeNote(id));
  const ph = usePhotos(id);

  useEffect(() => {
    api
      .get(id)
      .then((b) => {
        setBiz(b);
        setProfile(b.profile);
        setSubdomain(b.subdomain);
      })
      .catch(setLoadError);
    api.orders(id).then(setOrders).catch(() => setOrders([]));
    ph.load();
  }, [id]);

  if (loadError) return <ErrorBox error={loadError} />;
  if (!profile || !biz) return <p>Loading…</p>;

  const update = (patch: Partial<Profile>) => {
    setProfile({ ...profile, ...patch });
    setDirty(true);
  };
  const updateProduct = (i: number, patch: Partial<Product>) =>
    update({ products: profile.products.map((p, j) => (j === i ? { ...p, ...patch } : p)) });

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!profile) return;
    setSaving(true);
    setSaveError(null);
    try {
      const cleaned = {
        ...profile,
        products: profile.products.filter((p) => p.name.trim()),
        testimonials: profile.testimonials.filter((t) => t.name.trim() && t.text.trim()),
      };
      const b = await api.save(id, cleaned, subdomain);
      setBiz(b);
      setProfile(b.profile);
      setSubdomain(b.subdomain);
      setSavedAt(new Date());
      setDirty(false);
      ph.load(); // a renamed item keeps its photo; a removed item's photo is gone
    } catch (err) {
      setSaveError(err instanceof ApiError ? err : new ApiError(String(err), 0));
    } finally {
      setSaving(false);
    }
  }

  const host = biz.site_url ? new URL(biz.site_url).host.replace(/^[^.]+/, "") : "";

  return (
    <form onSubmit={save}>
      <StepHeader current="review" businessId={id} />
      <p className="eyebrow">Step 2 of 5 · review</p>
      <h1>Check your details</h1>
      <p className="tagline">This is what we understood. Fix anything that's wrong, then save — your website updates straight away.</p>
      {note && (
        <p className="muted assistant-note" role="status">
          {note}
        </p>
      )}

      <section className="card">
        {FIELDS.map((f) => (
          <label className="field" key={f.key}>
            <span>{f.label}</span>
            {f.long ? (
              <textarea rows={4} value={profile[f.key]} onChange={(e) => update({ [f.key]: e.target.value })} />
            ) : (
              <input value={profile[f.key]} onChange={(e) => update({ [f.key]: e.target.value })} />
            )}
            {f.hint && <small>{f.hint}</small>}
          </label>
        ))}
      </section>

      <h2>Where you sell</h2>
      <section className="card">
        <label className="check">
          <input
            type="checkbox"
            checked={modeParts(profile.selling_mode).pickup}
            onChange={(e) => update({ selling_mode: toMode(e.target.checked, modeParts(profile.selling_mode).kind) })}
          />
          <span>Customers can pick up</span>
        </label>
        {modeParts(profile.selling_mode).pickup && (
          <p className="muted small">
            Pickup: customers see only your area ({profile.area || "add it above"}
            {profile.city ? `, ${profile.city}` : ""}). You send the exact address on WhatsApp once you confirm the order.
          </p>
        )}
        <fieldset className="field">
          <legend>Delivery</legend>
          {(
            [
              ["none", "No delivery"],
              ["local", "I deliver locally (only to places I list)"],
              ["india", "I ship across India (by courier)"],
            ] as const
          ).map(([k, label]) => (
            <label className="check" key={k}>
              <input
                type="radio"
                name="delivery_kind"
                checked={modeParts(profile.selling_mode).kind === k}
                onChange={() => update({ selling_mode: toMode(modeParts(profile.selling_mode).pickup, k) })}
              />
              <span>{label}</span>
            </label>
          ))}
        </fieldset>
        {modeParts(profile.selling_mode).kind === "local" && (
          <>
            <label className="field">
              <span>Places you deliver to</span>
              <input
                value={profile.delivery_areas}
                maxLength={400}
                placeholder="e.g. Baner, Aundh, 411045"
                onChange={(e) => update({ delivery_areas: e.target.value })}
              />
              <small>Localities and/or 6-digit PIN codes, separated by commas. A customer outside these is told politely and can choose pickup instead.</small>
            </label>
            <label className="field">
              <span>Delivery charge (₹)</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={profile.delivery_fee_inr}
                onChange={(e) => update({ delivery_fee_inr: Math.max(0, Math.round(Number(e.target.value) || 0)) })}
              />
              <small>0 means free delivery.</small>
            </label>
            <label className="field">
              <span>Free delivery above (₹) (optional)</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={profile.free_delivery_above_inr}
                onChange={(e) => update({ free_delivery_above_inr: Math.max(0, Math.round(Number(e.target.value) || 0)) })}
              />
              <small>Orders worth this much or more get free delivery. 0 means never.</small>
            </label>
          </>
        )}
        {modeParts(profile.selling_mode).kind === "india" && (
          <>
            <label className="field">
              <span>Shipping charge (₹)</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={profile.shipping_fee_inr}
                onChange={(e) => update({ shipping_fee_inr: Math.max(0, Math.round(Number(e.target.value) || 0)) })}
              />
              <small>One flat charge per order. 0 means free shipping.</small>
            </label>
            <label className="field">
              <span>Days to dispatch an order</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                max={30}
                value={profile.dispatch_days}
                onChange={(e) => update({ dispatch_days: Math.min(30, Math.max(0, Math.round(Number(e.target.value) || 0))) })}
              />
            </label>
            <label className="field">
              <span>A note about shipping (optional)</span>
              <input
                value={profile.shipping_note}
                maxLength={120}
                placeholder="e.g. Ships via courier, tracking on WhatsApp"
                onChange={(e) => update({ shipping_note: e.target.value })}
              />
            </label>
          </>
        )}
      </section>

      <h2>When customers can order</h2>
      <section className="card">
        <label className="field">
          <span>Days of notice you need</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={60}
            value={profile.min_notice_days}
            onChange={(e) => update({ min_notice_days: Math.min(60, Math.max(0, Math.round(Number(e.target.value) || 0))) })}
          />
          <small>0 means customers can order for the same day. Customers can't pick a date sooner than this.</small>
        </label>
        <fieldset className="field">
          <legend>Days off (you don't deliver or hand over orders)</legend>
          <div className="weekdays">
            {WEEKDAYS.map((w, i) => (
              <label className="check" key={w}>
                <input
                  type="checkbox"
                  checked={profile.days_off.includes(i)}
                  onChange={(e) => {
                    const next = e.target.checked ? [...profile.days_off, i] : profile.days_off.filter((d) => d !== i);
                    update({ days_off: Array.from(new Set(next)).sort() });
                  }}
                />
                <span>{w}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="field">
          <span>Most orders you can take on one day (optional)</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={500}
            value={profile.max_orders_per_day}
            onChange={(e) => update({ max_orders_per_day: Math.min(500, Math.max(0, Math.round(Number(e.target.value) || 0))) })}
          />
          <small>When a day is full, customers can't pick it. 0 means no limit.</small>
        </label>
        <label className="field">
          <span>Time slots (optional)</span>
          <input
            value={slotsText ?? profile.time_slots.join(", ")}
            placeholder="e.g. 10am-1pm, 4pm-7pm"
            onChange={(e) => setSlotsText(e.target.value)}
            onBlur={() => {
              if (slotsText !== null) update({ time_slots: slotsText.split(",").map((x) => x.trim()).filter(Boolean).slice(0, 6) });
              setSlotsText(null);
            }}
          />
          <small>Customers can pick one of these when they order. Leave empty for no slot choice.</small>
        </label>
        <label className="check">
          <input type="checkbox" checked={profile.on_break} onChange={(e) => update({ on_break: e.target.checked })} />
          <span>I'm taking a break (the shop stays up but doesn't take orders)</span>
        </label>
        {profile.on_break && (
          <label className="field">
            <span>Back on (optional)</span>
            <input type="date" value={profile.back_on} onChange={(e) => update({ back_on: e.target.value })} />
            <small>Your shop says “Taking a break, back on …”. Orders start again on that day.</small>
          </label>
        )}
      </section>

      <h2>How customers pay</h2>
      <section className="card">
        <fieldset className="field">
          <legend>Payment</legend>
          {(
            [
              ["upfront", "Full payment upfront (by UPI after they order)"],
              ["advance", "An advance, the rest on delivery or pickup"],
              ["on_delivery", "Pay when they collect or receive it"],
            ] as const
          ).map(([k, label]) => (
            <label className="check" key={k}>
              <input
                type="radio"
                name="payment_terms"
                checked={profile.payment_terms === k}
                onChange={() => update({ payment_terms: k, advance_percent: k === "advance" ? profile.advance_percent || 50 : profile.advance_percent })}
              />
              <span>{label}</span>
            </label>
          ))}
        </fieldset>
        {profile.payment_terms === "advance" && (
          <label className="field">
            <span>Advance (% of the total)</span>
            <input
              type="number"
              inputMode="numeric"
              min={10}
              max={90}
              value={profile.advance_percent}
              onChange={(e) => update({ advance_percent: Math.round(Number(e.target.value) || 0) })}
            />
            <small>Between 10 and 90. The customer's UPI link asks for exactly this amount, with the order number in the note.</small>
          </label>
        )}
        <label className="check">
          <input type="checkbox" checked={profile.accepts_cash} onChange={(e) => update({ accepts_cash: e.target.checked })} />
          <span>I also accept cash</span>
        </label>
        <label className="field">
          <span>Cancellation and refunds</span>
          <select
            value={profile.cancellation_preset}
            onChange={(e) => update({ cancellation_preset: e.target.value as Profile["cancellation_preset"] })}
          >
            {CANCEL_PRESETS.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
          <small>Shown on your shop and in the order email.</small>
        </label>
        {profile.cancellation_preset === "custom" && (
          <label className="field">
            <span>Your cancellation line</span>
            <input value={profile.cancellation_text} maxLength={140} onChange={(e) => update({ cancellation_text: e.target.value })} />
          </label>
        )}
      </section>

      <h2>How customers order</h2>
      <section className="card">
        <label className="field">
          <span>What makes you special (optional)</span>
          <input
            value={profile.selling_point}
            maxLength={40}
            placeholder="e.g. Home-style, Handmade"
            onChange={(e) => update({ selling_point: e.target.value })}
          />
          <small>A few words shown as a label at the top of your site. Leave empty to show nothing.</small>
        </label>
        <label className="field">
          <span>What kind of shop is it?</span>
          <select value={profile.niche} onChange={(e) => update({ niche: e.target.value as Profile["niche"] })}>
            <option value="">Not sure</option>
            <option value="food">Home food (cakes, tiffin, pickles, snacks)</option>
            <option value="handmade">Handmade goods (candles, crafts, jewellery, hampers)</option>
            <option value="custom">Custom work (tailoring, embroidery, art)</option>
          </select>
          <small>It helps us suggest a look for your shop.</small>
        </label>
        <label className="field">
          <span>Allergens (optional, for food)</span>
          <input
            value={profile.allergens}
            maxLength={200}
            placeholder="e.g. Contains nuts, gluten and dairy"
            onChange={(e) => update({ allergens: e.target.value })}
          />
          <small>Shown on your shop. We may have suggested this from what you wrote: please check it.</small>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={profile.allow_item_message}
            onChange={(e) => update({ allow_item_message: e.target.checked })}
          />
          <span>Customers can add a message for the item (for example a name to write on it)</span>
        </label>
      </section>

      <h2>Photos</h2>
      <p className="muted">Real photos make your shop look like yours. Without them, your shop keeps its plain design.</p>
      <ShopPhotos ph={ph} />

      <h2>The look of your shop</h2>
      <ThemePicker
        biz={biz}
        onSaved={(b) => {
          setBiz(b);
          setProfile((p) => (p ? { ...p, theme: b.profile.theme, accent: b.profile.accent } : p));
        }}
      />

      <h2>Words on your page</h2>
      <p className="muted">
        We wrote these from what you told us. Change anything that isn't right. Leave a box empty and that spot uses your
        other details instead. (The “About” text is the one in your details above.)
      </p>
      <section className="card copy-fields">
        <label className="field">
          <span>Big headline</span>
          <input
            value={profile.section_copy.hero_line}
            maxLength={90}
            onChange={(e) => update({ section_copy: { ...profile.section_copy, hero_line: e.target.value } })}
          />
        </label>
        <label className="field">
          <span>How ordering works (one line)</span>
          <input
            value={profile.section_copy.how_ordering}
            maxLength={160}
            onChange={(e) => update({ section_copy: { ...profile.section_copy, how_ordering: e.target.value } })}
          />
        </label>
      </section>

      <h2>Kind words from customers (optional)</h2>
      <p className="muted">
        Only add real messages your customers sent you. We never write these. They're shown as “shared by the seller”.
      </p>
      <section className="card">
        {profile.testimonials.map((t, i) => (
          <div className="quote-row" key={i}>
            <label className="field">
              <span>Customer's name</span>
              <input
                value={t.name}
                maxLength={60}
                onChange={(e) => update({ testimonials: profile.testimonials.map((q, j) => (j === i ? { ...q, name: e.target.value } : q)) })}
              />
            </label>
            <label className="field">
              <span>What they said</span>
              <textarea
                rows={2}
                value={t.text}
                maxLength={300}
                onChange={(e) => update({ testimonials: profile.testimonials.map((q, j) => (j === i ? { ...q, text: e.target.value } : q)) })}
              />
            </label>
            <button type="button" className="btn btn-ghost" onClick={() => update({ testimonials: profile.testimonials.filter((_, j) => j !== i) })}>
              Remove
            </button>
          </div>
        ))}
        {profile.testimonials.length < 6 && (
          <button type="button" className="btn btn-ghost" onClick={() => update({ testimonials: [...profile.testimonials, { name: "", text: "" }] })}>
            + Add a message
          </button>
        )}
      </section>

      <h2>Menu and prices</h2>
      <p className="muted">Items with the same group are shown together on your site.</p>
      <section className="card products">
        {profile.products.map((p, i) => (
          <div className="product" key={i}>
            <label className="field grow">
              <span>Item</span>
              <input value={p.name} onChange={(e) => updateProduct(i, { name: e.target.value })} />
            </label>
            <label className="field price">
              <span>Price (₹)</span>
              <input
                type="number"
                inputMode="numeric"
                min={0}
                value={p.price_inr}
                onChange={(e) => updateProduct(i, { price_inr: Math.max(0, Math.round(Number(e.target.value) || 0)) })}
              />
            </label>
            <label className="field">
              <span>Group</span>
              <input value={p.category} onChange={(e) => updateProduct(i, { category: e.target.value })} />
            </label>
            <label className="field grow">
              <span>Short description</span>
              <input value={p.description} onChange={(e) => updateProduct(i, { description: e.target.value })} />
            </label>
            <label className="check">
              <input type="checkbox" checked={p.addon} onChange={(e) => updateProduct(i, { addon: e.target.checked })} />
              <span>Extra (only added to another item)</span>
            </label>
            <label className="field">
              <span>Food mark</span>
              <select value={p.food_mark} onChange={(e) => updateProduct(i, { food_mark: e.target.value as Product["food_mark"] })}>
                <option value="">Not food / not marked</option>
                <option value="veg">Veg</option>
                <option value="egg">Contains egg</option>
                <option value="nonveg">Non-veg</option>
              </select>
              {p.food_mark === "" ? null : <small>Shown with the green / brown mark and the word. Please check it's right.</small>}
            </label>
            <ItemPhoto ph={ph} saved={biz.profile.products[i]?.name ?? ""} dirty={dirty} />
            <label className="check">
              <input type="checkbox" checked={p.price_from} onChange={(e) => updateProduct(i, { price_from: e.target.checked })} />
              <span>Starting price (“from ₹…”)</span>
            </label>
            <button
              type="button"
              className="btn btn-ghost remove"
              aria-label={`Remove ${p.name || "item"}`}
              onClick={() => update({ products: profile.products.filter((_, j) => j !== i) })}
            >
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() =>
            update({ products: [...profile.products, emptyProduct(profile.products[profile.products.length - 1]?.category ?? "Menu")] })
          }
        >
          + Add an item
        </button>
      </section>

      <h2>Your website address</h2>
      <section className="card">
        <label className="field">
          <span>Address</span>
          <div className="address">
            <input
              value={subdomain}
              onChange={(e) => {
                setSubdomain(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""));
                setDirty(true);
              }}
              maxLength={42}
            />
            <span className="muted">{host}</span>
          </div>
          <small>A free address to start with. You can get your own name later.</small>
        </label>
      </section>

      <p className="muted" role="note">
        {biz.owner_email
          ? <>Orders and warnings go to your sign-in address, <strong>{biz.owner_email}</strong>.</>
          : <>This is a practice shop. <a href="#/signin">Sign in</a> to keep it; orders then go to your sign-in address.</>}
      </p>

      {saveError && <ErrorBox error={saveError} />}
      <div className="actions">
        <button className="btn btn-primary" type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <ShopLink businessId={id} siteUrl={biz.site_url} isPublic={biz.public} label="View my shop" />
        {!dirty && biz.status !== "live" && (
          <a className="btn btn-primary" href={`#/b/${id}/launch`}>
            Launch my website →
          </a>
        )}
        {!dirty && biz.status === "live" && (
          <a className="btn btn-primary" href={`#/b/${id}/report`}>
            See your launch report →
          </a>
        )}
        {savedAt && !dirty && <span className="saved">✅ Saved. Your website is up to date.</span>}
        {dirty && <span className="muted">You have unsaved changes.</span>}
      </div>

      <GoLiveCard businessId={id} version={savedAt ? savedAt.getTime() : 0} />

      {orders.length > 0 && (
        <p className="card">
          {orders.length} order{orders.length === 1 ? "" : "s"} from your website
          {orders.some((o) => o.status === "new") ? `, ${orders.filter((o) => o.status === "new").length} new` : ""}.{" "}
          <a href={`#/b/${id}/orders`}>See your orders →</a>
        </p>
      )}
    </form>
  );
}
