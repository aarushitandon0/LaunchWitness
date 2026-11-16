/** S12: product photos on the Review step. Up to 6 for the shop, plus one per item. The server checks each file by its
 *  content, re-encodes it and removes everything but the picture (no location, no camera details). */
import { useRef, useState } from "react";
import { api, ApiError, PhotoList, PhotoOut } from "./api";

const ACCEPT = "image/jpeg,image/png,image/webp";

export function usePhotos(id: number) {
  const [list, setList] = useState<PhotoList | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = () => api.photos(id).then(setList).catch(() => setList(null));
  const run = async (key: string, fn: () => Promise<PhotoList>) => {
    setBusy(key);
    setError("");
    try {
      setList(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That didn't work. Please try again.");
    } finally {
      setBusy("");
    }
  };
  return { list, error, busy, load, add: (f: File, item = "") => run(item || "shop", () => api.addPhoto(id, f, item)),
    remove: (p: PhotoOut) => run(p.item || `shop-${p.id}`, () => api.removePhoto(id, p.id)) };
}

function Picker({ label, onPick, disabled }: { label: string; onPick: (f: File) => void; disabled?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className="btn btn-ghost btn-sm" disabled={disabled} onClick={() => ref.current?.click()}>
        {label}
      </button>
      <input
        ref={ref}
        type="file"
        accept={ACCEPT}
        hidden
        aria-label={label}
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) onPick(f);
        }}
      />
    </>
  );
}

export function ShopPhotos({ ph }: { ph: ReturnType<typeof usePhotos> }) {
  const list = ph.list;
  if (!list) return null;
  const full = list.shop.length >= list.max_shop;
  return (
    <section className="card photos-card" aria-labelledby="photos-h">
      <h3 id="photos-h">Shop photos</h3>
      <p className="muted small">
        Up to {list.max_shop}, shown near the top of your shop. JPEG, PNG or WebP, under {list.max_mb} MB. We remove the
        location and camera details from every photo before saving it.
      </p>
      {list.shop.length > 0 && (
        <ul className="photo-grid">
          {list.shop.map((p) => (
            <li key={p.id}>
              <img src={p.small} width={p.small_w} height={p.small_h} alt={p.alt} loading="lazy" />
              <button type="button" className="btn btn-ghost btn-sm" disabled={!!ph.busy} onClick={() => ph.remove(p)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="actions">
        <Picker
          label={ph.busy === "shop" ? "Adding…" : "Add a shop photo"}
          disabled={full || !!ph.busy}
          onPick={(f) => ph.add(f)}
        />
        <span className="muted small">
          {list.shop.length} of {list.max_shop}
          {full ? ": remove one to add another" : ""}
        </span>
      </div>
      {ph.error && (
        <p className="error" role="alert">
          {ph.error}
        </p>
      )}
    </section>
  );
}

/** One item's photo, inside its row. `saved`: the item's name as last saved (photos follow the saved list). */
export function ItemPhoto({ ph, saved, dirty }: { ph: ReturnType<typeof usePhotos>; saved: string; dirty: boolean }) {
  const p = ph.list?.items[saved];
  if (!ph.list) return null;
  return (
    <div className="item-photo-row">
      {p && <img src={p.small} width={56} height={56} alt={p.alt} loading="lazy" className="item-thumb" />}
      <Picker
        label={ph.busy === saved ? "Adding…" : p ? `Change photo of ${saved}` : `Add a photo of ${saved}`}
        disabled={dirty || !!ph.busy || !saved}
        onPick={(f) => ph.add(f, saved)}
      />
      {p && (
        <button type="button" className="btn btn-ghost btn-sm" disabled={!!ph.busy} onClick={() => ph.remove(p)}>
          Remove photo
        </button>
      )}
      {dirty && <small className="muted">Save your changes first to add a photo here.</small>}
    </div>
  );
}
