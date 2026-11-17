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
    ? K extends "kind" | "not_supported_reason" | "niche" | "delivery_areas" | "theme" | "accent"
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
    hint: "Neighbourhood and city, e.g. Baner, Pune. Only this is shown, never your home address: you share the exact pickup address yourself on WhatsApp after you confirm an order.",
  },
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
});

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
          <span>Days of notice you need</span>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={60}
            value={profile.min_notice_days}
            onChange={(e) => update({ min_notice_days: Math.min(60, Math.max(0, Math.round(Number(e.target.value) || 0))) })}
          />
          <small>0 means customers can order for the same day.</small>
        </label>
        <label className="check">
          <input type="checkbox" checked={profile.pickup_available} onChange={(e) => update({ pickup_available: e.target.checked })} />
          <span>Customers can pick up</span>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={profile.delivery_available}
            onChange={(e) => update({ delivery_available: e.target.checked })}
          />
          <span>I deliver</span>
        </label>
        {profile.delivery_available && (
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
        )}
        {profile.delivery_available && (
          <label className="field">
            <span>Areas you deliver to</span>
            <input
              value={profile.delivery_areas}
              maxLength={200}
              placeholder="e.g. Baner, Aundh, Pashan"
              onChange={(e) => update({ delivery_areas: e.target.value })}
            />
          </label>
        )}
        {profile.pickup_available && (
          <p className="muted small">
            Pickup: customers see only your area ({profile.area || "add it above"}). You send the exact address on
            WhatsApp once you confirm the order.
          </p>
        )}
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
