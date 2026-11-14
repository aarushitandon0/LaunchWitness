import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, Business, inr, Order, Product, Profile } from "./api";
import { ErrorBox } from "./Describe";

type TextKey = Exclude<keyof Profile, "products">;

const FIELDS: { key: TextKey; label: string; hint?: string; long?: boolean }[] = [
  { key: "name", label: "Business name" },
  { key: "tagline", label: "One line about you", hint: "Shown at the top of your site." },
  { key: "about", label: "About", long: true },
  { key: "area", label: "Area", hint: "Neighbourhood and city." },
  { key: "hours", label: "Opening hours" },
  { key: "phone", label: "Phone number" },
  { key: "whatsapp", label: "WhatsApp number", hint: "Customers get an “Order on WhatsApp” button." },
  { key: "upi_id", label: "UPI ID", hint: "e.g. yourname@okaxis — we show a QR code customers can scan to pay." },
];

const emptyProduct = (category: string): Product => ({ name: "", price_inr: 0, description: "", category });

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
      const cleaned = { ...profile, products: profile.products.filter((p) => p.name.trim()) };
      const b = await api.save(id, cleaned, subdomain);
      setBiz(b);
      setProfile(b.profile);
      setSubdomain(b.subdomain);
      setSavedAt(new Date());
      setDirty(false);
    } catch (err) {
      setSaveError(err instanceof ApiError ? err : new ApiError(String(err), 0));
    } finally {
      setSaving(false);
    }
  }

  const host = biz.site_url ? new URL(biz.site_url).host.replace(/^[^.]+/, "") : "";

  return (
    <form onSubmit={save}>
      <h1>Check your details</h1>
      <p className="tagline">This is what we understood. Fix anything that's wrong, then save — your website updates straight away.</p>

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

      {saveError && <ErrorBox error={saveError} />}
      <div className="actions">
        <button className="btn btn-primary" type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        {biz.site_url && (
          <a className="btn btn-ghost" href={biz.site_url} target="_blank" rel="noreferrer">
            View my website
          </a>
        )}
        {!dirty && (
          <a className="btn btn-primary" href={`#/b/${id}/launch`}>
            Launch my website →
          </a>
        )}
        {savedAt && !dirty && <span className="saved">✅ Saved. Your website is up to date.</span>}
        {dirty && <span className="muted">You have unsaved changes.</span>}
      </div>

      {orders.length > 0 && (
        <>
          <h2>Orders from your website</h2>
          <ul className="card orders">
            {orders.map((o) => (
              <li key={o.id}>
                <strong>
                  #{o.id} · {o.customer_name}
                </strong>{" "}
                <span className="muted">
                  {o.customer_phone} · {new Date(o.created_at).toLocaleString()}
                </span>
                <div>
                  {o.items.map((it) => `${it.qty} × ${it.name}`).join(", ") || "See note"} — {inr(o.total_inr)}
                </div>
                {o.note && <div className="muted">“{o.note}”</div>}
                {o.email_status !== "sent" && <div className="warn">We couldn't email this order to you yet.</div>}
              </li>
            ))}
          </ul>
        </>
      )}
    </form>
  );
}
