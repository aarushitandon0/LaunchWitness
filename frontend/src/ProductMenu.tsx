import { useEffect, useId, useRef, useState } from "react";

/** The "Product" menu: four short columns. Every link goes to a landing section or a page that exists. */
const COLUMNS: { title: string; links: [string, string][] }[] = [
  {
    title: "What it does",
    links: [
      ["Launch your shop", "#how"],
      ["Prove a real order arrives", "#proof"],
      ["Fix what breaks", "#fix"],
      ["Keep watching", "#watch"],
    ],
  },
  {
    title: "Who it's for",
    links: [
      ["Home food", "#who-food"],
      ["Handmade goods", "#who-handmade"],
      ["Custom work", "#who-custom"],
    ],
  },
  {
    title: "Free tools",
    links: [
      ["Check any address", "#check"],
      ["See a demo shop", "/demo/meera"],
    ],
  },
  {
    title: "Learn",
    links: [
      ["How the proof works", "#proof"],
      ["Security & privacy", "#security"],
      ["Build log", "/build"],
    ],
  },
];

/** Keyboard accessible: a real button (aria-expanded), Esc closes and returns focus, an outside click closes,
 * choosing a link closes. On phones the panel is a full-screen sheet with its own Close button. */
export function ProductMenu() {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !button.current?.contains(t)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    panel.current?.querySelector("a")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  return (
    <span className="product-menu">
      <button
        ref={button}
        type="button"
        className="product-button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        Product <span aria-hidden>{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div ref={panel} id={id} className="product-panel" role="region" aria-label="Product">
          <div className="product-sheet-head">
            <strong>Product</strong>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setOpen(false);
                button.current?.focus();
              }}
            >
              Close
            </button>
          </div>
          <div className="product-cols">
            {COLUMNS.map((c) => (
              <div key={c.title} className="product-col">
                <p className="product-col-title">{c.title}</p>
                <ul>
                  {c.links.map(([label, href]) => (
                    <li key={label}>
                      <a href={href} onClick={() => setOpen(false)}>
                        {label}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </span>
  );
}
