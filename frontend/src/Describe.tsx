import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, Sample } from "./api";
import { goTo } from "./App";
import { rememberNote } from "./Report";
import { StepHeader } from "./Steps";

export default function Describe({ guest = false }: { guest?: boolean }) {
  const [description, setDescription] = useState("");
  const [priceList, setPriceList] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);

  useEffect(() => {
    api.samples().then(setSamples).catch(() => setSamples([]));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const b = await api.create(description, priceList, photo);
      if (b.assistant_note) rememberNote(b.id, b.assistant_note);
      goTo(`#/b/${b.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(String(err), 0));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <StepHeader current="describe" />
      <p className="eyebrow">Step 1 of 5 · describe{guest ? " · practice" : ""}</p>
      <h1>Describe your business</h1>
      {guest && (
        <p className="practice" role="note">
          Practice only, without an account: your shop can't go live and is deleted after 24 hours.{" "}
          <a href="#/signin?next=new">Sign in</a> to keep it and launch for real.
        </p>
      )}
      <p className="tagline">
        Tell us in your own words what you sell, where, and when you're open. Paste your price list or add a photo of
        it. We'll turn it into your website — you can check and change everything next.
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
              }}
            >
              {s.owner_name}, {s.city}
            </button>
          ))}
        </p>
      )}

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
        <label className="field">
          <span>Price list</span>
          <textarea
            rows={6}
            value={priceList}
            onChange={(e) => setPriceList(e.target.value)}
            placeholder={"Chocolate cake 1/2 kg - ₹650\nCupcakes box of 6 - ₹420"}
            maxLength={4000}
          />
        </label>
        <label className="field">
          <span>Or a photo of your menu / price list (optional)</span>
          <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
        </label>
        {error && <ErrorBox error={error} />}
        <button className="btn btn-primary" type="submit" disabled={busy || (!description.trim() && !priceList.trim() && !photo)}>
          {busy ? "Reading your business…" : "Make my website"}
        </button>
      </form>

      <p className="muted">
        Already made one? <a href="#/shops">{guest ? "See your practice shops" : "See your shops"}</a>.
      </p>
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
