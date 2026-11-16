import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { PREVIEWED_EVENT } from "./GoLive";

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
  const frame = useRef<HTMLIFrameElement>(null);
  const open_ = html !== null;

  useEffect(() => {
    if (!open_) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setHtml(null);
    // The shop page asks for its own pages (home, privacy) by name. Only a message from OUR preview frame counts,
    // and only those two names; nothing else in the message is used.
    const onMessage = (e: MessageEvent) => {
      if (!frame.current || e.source !== frame.current.contentWindow) return;
      const page = (e.data as { lwPreview?: unknown } | null)?.lwPreview;
      if (page !== "home" && page !== "privacy") return;
      api.preview(businessId, page).then(setHtml).catch(() => setError("We couldn't load that page of the preview."));
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("message", onMessage);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("message", onMessage);
    };
  }, [open_, businessId]);

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
      window.dispatchEvent(new Event(PREVIEWED_EVENT)); // the go-live checklist ticks "looked at your preview"
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
          {/* sandbox WITHOUT allow-same-origin: the shop page gets an opaque origin, so it can run its own basket and
              link script but can't read this app, its cookies or its storage. allow-popups(+to-escape-sandbox): WhatsApp,
              Instagram and phone links open as normal new tabs (noopener). No allow-forms / allow-top-navigation. */}
          <iframe
            ref={frame}
            title="Preview of your shop"
            sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
            srcDoc={html}
          />
        </div>
      )}
    </>
  );
}
