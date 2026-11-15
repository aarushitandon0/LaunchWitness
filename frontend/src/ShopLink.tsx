import { useEffect, useState } from "react";
import { api, ApiError } from "./api";

/**
 * Link to a seller's shop. A public (live, real) shop opens at its own address.
 * A draft or practice shop is never public, so its owner sees a private preview instead:
 * the page is fetched with the owner's access and shown in a locked-down frame.
 */
export function ShopLink({
  businessId,
  siteUrl,
  isPublic,
  label = "Open my shop",
}: {
  businessId: number;
  siteUrl: string | null;
  isPublic: boolean;
  label?: string;
}) {
  const [html, setHtml] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (html === null) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setHtml(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [html]);

  if (isPublic && siteUrl) {
    return (
      <a className="btn btn-ghost" href={siteUrl} target="_blank" rel="noreferrer">
        {label}
      </a>
    );
  }

  const open = async () => {
    setBusy(true);
    setError("");
    try {
      setHtml(await api.preview(businessId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "We couldn't load the preview. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button className="btn btn-ghost" type="button" onClick={open} disabled={busy}>
        {busy ? "Opening…" : "Preview my shop"}
      </button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {html !== null && (
        <div className="preview-overlay" role="dialog" aria-modal="true" aria-label="Preview of your shop">
          <div className="preview-bar">
            <span>Private preview. Only you can see this; it is not on the internet yet.</span>
            <button className="btn btn-ghost" type="button" onClick={() => setHtml(null)} autoFocus>
              Close
            </button>
          </div>
          {/* sandbox without allow-same-origin: the page can run its own basket script but can't touch this app */}
          <iframe title="Preview of your shop" sandbox="allow-scripts" srcDoc={html} />
        </div>
      )}
    </>
  );
}
