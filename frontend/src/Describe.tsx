import { FormEvent, useEffect, useRef, useState } from "react";
import { api, ApiError, Business, Sample } from "./api";
import { goTo } from "./App";
import { rememberNote } from "./Report";
import { StepHeader } from "./Steps";

/** S17: what she sells, one row per item, each with its own photo. The rows are sent to the Reader as the same
 *  "name - ₹price" lines a pasted list would be (no prompt change); each photo is attached to the item the Reader
 *  made from its row once the shop exists (the server matches her words: app/photos.py::match_item). */
type Row = {
  key: number;
  name: string;
  price: string;
  photo: File | null;
  preview: string | null;
  error: string;
};

const ACCEPT = "image/jpeg,image/png,image/webp";
const MAX_PHOTO_MB = 7; // app/photos.py MAX_UPLOAD_BYTES
let nextKey = 1;
const emptyRow = (name = "", price = ""): Row => ({
  key: nextKey++,
  name,
  price,
  photo: null,
  preview: null,
  error: "",
});

/** "650" -> "₹650"; anything else ("from 300", "₹1,200", "Rs 80") as she wrote it. */
export function priceText(price: string): string {
  const p = price.trim();
  return /^\d+(?:[.,]\d+)*$/.test(p) ? `₹${p}` : p;
}

/** The rows as a price list, one "name - price" line per filled row. */
export function rowsToList(rows: { name: string; price: string }[]): string {
  return rows
    .filter((r) => r.name.trim())
    .map((r) =>
      r.price.trim()
        ? `${r.name.trim()} - ${priceText(r.price)}`
        : r.name.trim(),
    )
    .join("\n");
}

/** A pasted list back into rows (for the examples): the price is after the last " - ". */
export function listToRows(list: string): { name: string; price: string }[] {
  return list
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const i = l.lastIndexOf(" - ");
      return i > 0
        ? { name: l.slice(0, i).trim(), price: l.slice(i + 3).trim() }
        : { name: l, price: "" };
    });
}

/** `businessId` (S17): back to Describe for a shop she already made. Her saved words come back; "Read it again"
 *  re-reads them for THIS shop (same address, no second shop), only before launch. */
export default function Describe({
  guest = false,
  businessId,
}: {
  guest?: boolean;
  businessId?: number;
}) {
  const again = businessId !== undefined;
  const [biz, setBiz] = useState<Business | null>(null);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState<"rows" | "paste">("rows");
  const [rows, setRows] = useState<Row[]>(() => [emptyRow(), emptyRow()]);
  const [priceList, setPriceList] = useState("");
  const [menuPhoto, setMenuPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<ApiError | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;

  useEffect(() => {
    if (again) return;
    api
      .samples()
      .then(setSamples)
      .catch(() => setSamples([]));
  }, [again]);
  useEffect(() => {
    if (businessId === undefined) return;
    api
      .get(businessId)
      .then((b) => {
        setBiz(b);
        setDescription(b.description ?? "");
        const words = b.price_list ?? "";
        const parsed = listToRows(words).map((r) => emptyRow(r.name, r.price));
        setPriceList(words);
        if (parsed.length) setRows(parsed);
        else if (words.trim()) setMode("paste");
      })
      .catch((e) =>
        setLoadError(e instanceof ApiError ? e : new ApiError(String(e), 0)),
      );
  }, [businessId]);
  const launched =
    !!biz &&
    (biz.status === "live" ||
      biz.latest_plan?.status === "approved" ||
      biz.latest_plan?.status === "running");
  // Free the photo previews when she leaves the page.
  useEffect(
    () => () =>
      rowsRef.current.forEach(
        (r) => r.preview && URL.revokeObjectURL(r.preview),
      ),
    [],
  );

  const update = (key: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  function pickPhoto(row: Row, f: File | null) {
    if (row.preview) URL.revokeObjectURL(row.preview);
    if (f && f.size > MAX_PHOTO_MB * 1024 * 1024) {
      update(row.key, {
        photo: null,
        preview: null,
        error: `That photo is too big. Please use one under ${MAX_PHOTO_MB} MB.`,
      });
      return;
    }
    update(row.key, {
      photo: f,
      preview: f ? URL.createObjectURL(f) : null,
      error: "",
    });
  }

  function removeRow(row: Row) {
    if (row.preview) URL.revokeObjectURL(row.preview);
    setRows((rs) =>
      rs.length > 1 ? rs.filter((r) => r.key !== row.key) : [emptyRow()],
    );
  }

  const list = mode === "rows" ? rowsToList(rows) : priceList;
  const ready =
    description.trim() || list.trim() || (mode === "paste" && menuPhoto);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy("Reading your business…");
    setError(null);
    try {
      const photo = mode === "paste" ? menuPhoto : null;
      const b = again
        ? await api.reread(businessId, description, list, photo)
        : await api.create(description, list, photo);
      const notes: string[] = b.assistant_note ? [b.assistant_note] : [];
      const withPhotos =
        mode === "rows" ? rows.filter((r) => r.photo && r.name.trim()) : [];
      const missed: string[] = [];
      for (const [i, r] of withPhotos.entries()) {
        setBusy(`Adding your photos (${i + 1} of ${withPhotos.length})…`);
        try {
          await api.addItemPhoto(b.id, r.photo as File, r.name.trim());
        } catch {
          missed.push(r.name.trim());
        }
      }
      if (missed.length)
        notes.push(
          `We couldn't add the photo for ${missed.map((n) => `“${n}”`).join(", ")}. ` +
            "Add it below, next to the item: nothing else was lost.",
        );
      if (notes.length) rememberNote(b.id, notes.join(" "));
      goTo(`#/b/${b.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(String(err), 0));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <StepHeader current="describe" businessId={businessId} />
      <p className="eyebrow">
        Step 1 of 5 · describe{guest ? " · practice" : ""}
      </p>
      <h1>Describe your business</h1>
      {loadError && <ErrorBox error={loadError} />}
      {again && launched && (
        <div className="status" role="note">
          <p>
            Your shop is already launched, so it can't be read again from
            scratch. Change its details on the{" "}
            <a href={`#/b/${businessId}`}>Review page</a> instead.
          </p>
        </div>
      )}
      {again && biz && !launched && (
        <p className="status" role="note">
          These are the words you gave us. Change anything, then{" "}
          <strong>Read it again</strong>: the details on the next page are
          replaced with the new reading, for this same shop and address.
          Anything it doesn't find (like your WhatsApp, UPI or delivery areas)
          stays as you set it.{" "}
          <a href={`#/b/${businessId}`}>Back to Review without changes</a>
        </p>
      )}
      {guest && (
        <p className="practice" role="note">
          Practice only, without an account: your shop can't go live and is
          deleted after 24 hours. <a href="#/signin?next=new">Sign in</a> to
          keep it and launch for real.
        </p>
      )}
      <p className="tagline">
        Tell us in your own words what you sell, where, and when you're open.
        Then add each thing you sell with its price and a photo. We'll turn it
        into your website — you can check and change everything next.
      </p>

      {samples.length > 0 && (
        <p className="samples">
          Try an example:{" "}
          {samples.map((s) => (
            <button
              key={s.id}
              type="button"
              className="chip"
              onClick={() => {
                setDescription(s.description);
                setPriceList(s.price_list);
                rows.forEach(
                  (r) => r.preview && URL.revokeObjectURL(r.preview),
                );
                const parsed = listToRows(s.price_list).map((r) =>
                  emptyRow(r.name, r.price),
                );
                setRows(parsed.length ? parsed : [emptyRow()]);
              }}
            >
              {s.owner_name}, {s.city}
            </button>
          ))}
        </p>
      )}

      {(!again || (biz && !launched)) && (
        <form className="card" onSubmit={submit}>
          <label className="field">
            <span>About your business</span>
            <textarea
              rows={6}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="I make … at home in (area, city). Customers order on Instagram and WhatsApp, at least … days ahead…"
              maxLength={4000}
            />
          </label>

          {mode === "rows" ? (
            <fieldset className="field item-rows">
              <legend>What you sell</legend>
              <small>
                One line per item: its name (with the size, if it has one), the
                price, and a photo if you have one.
              </small>
              <ol className="item-list">
                {rows.map((r, i) => (
                  <li key={r.key} className="item-entry">
                    <div className="item-entry-fields">
                      <input
                        aria-label={`Item ${i + 1} name`}
                        value={r.name}
                        onChange={(e) =>
                          update(r.key, { name: e.target.value })
                        }
                        placeholder={
                          i === 0
                            ? "Chocolate truffle cake 1/2 kg"
                            : "Item name"
                        }
                        maxLength={120}
                      />
                      <input
                        aria-label={`Item ${i + 1} price`}
                        className="item-price"
                        value={r.price}
                        inputMode="decimal"
                        onChange={(e) =>
                          update(r.key, { price: e.target.value })
                        }
                        placeholder="₹ price"
                        maxLength={40}
                      />
                    </div>
                    <div className="item-photo-row">
                      {r.preview && (
                        <img
                          src={r.preview}
                          alt=""
                          width={56}
                          height={56}
                          className="item-thumb"
                        />
                      )}
                      <PhotoButton
                        label={r.photo ? "Change photo" : "Add photo"}
                        inputLabel={`Photo of item ${i + 1}${r.name.trim() ? `: ${r.name.trim()}` : ""}`}
                        onPick={(f) => pickPhoto(r, f)}
                      />
                      {r.photo && (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => pickPhoto(r, null)}
                        >
                          Remove photo
                        </button>
                      )}
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        aria-label={`Remove item ${i + 1}`}
                        onClick={() => removeRow(r)}
                      >
                        Remove item
                      </button>
                    </div>
                    {r.error && (
                      <p className="error small" role="alert">
                        {r.error}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
              <div className="actions">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setRows((rs) => [...rs, emptyRow()])}
                  disabled={rows.length >= 60}
                >
                  + Add another item
                </button>
                <button
                  type="button"
                  className="link-like"
                  onClick={() => {
                    setPriceList(rowsToList(rows) || priceList);
                    setMode("paste");
                  }}
                >
                  Paste a whole list instead
                </button>
              </div>
            </fieldset>
          ) : (
            <>
              <label className="field">
                <span>Price list</span>
                <textarea
                  rows={6}
                  value={priceList}
                  onChange={(e) => setPriceList(e.target.value)}
                  placeholder={
                    "Chocolate cake 1/2 kg - ₹650\nCupcakes box of 6 - ₹420"
                  }
                  maxLength={4000}
                />
              </label>
              <label className="field">
                <span>
                  Or a photo of your printed or handwritten menu (optional)
                </span>
                <input
                  type="file"
                  accept={ACCEPT}
                  onChange={(e) => setMenuPhoto(e.target.files?.[0] ?? null)}
                />
              </label>
              <p className="small muted">
                You can add a photo of each item on the next page.{" "}
                <button
                  type="button"
                  className="link-like"
                  onClick={() => {
                    const parsed = listToRows(priceList).map((r) =>
                      emptyRow(r.name, r.price),
                    );
                    if (parsed.length) setRows(parsed);
                    setMode("rows");
                  }}
                >
                  Add items one by one, with photos
                </button>
              </p>
            </>
          )}

          {error && <ErrorBox error={error} />}
          <button
            className="btn btn-primary"
            type="submit"
            disabled={!!busy || !ready}
          >
            {busy || (again ? "Read it again" : "Make my website")}
          </button>
        </form>
      )}

      {!again && (
        <p className="muted">
          Already made one?{" "}
          <a href="#/shops">
            {guest ? "See your practice shops" : "See your shops"}
          </a>
          .
        </p>
      )}
    </>
  );
}

function PhotoButton({
  label,
  inputLabel,
  onPick,
}: {
  label: string;
  inputLabel: string;
  onPick: (f: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => ref.current?.click()}
      >
        {label}
      </button>
      <input
        ref={ref}
        type="file"
        accept={ACCEPT}
        hidden
        aria-label={inputLabel}
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (f) onPick(f);
        }}
      />
    </>
  );
}

export function ErrorBox({ error }: { error: ApiError }) {
  return (
    <div className="status status-error" role="alert">
      <p>{error.message}</p>
      {error.status === 404 && (
        <p>
          <a href="#/shops">Back to My shops</a>
        </p>
      )}
      {error.details !== null && typeof error.details !== "string" && (
        <details>
          <summary>Details</summary>
          <pre>{JSON.stringify(error.details, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
