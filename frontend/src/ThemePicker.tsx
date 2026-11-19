import { useEffect, useState } from "react";
import { api, ApiError, Business, ThemeInfo } from "./api";

/** A small picture of a theme: its colours, its hero layout and its corner radius, drawn with the seller's own name. */
function Thumb({ t, accent, name }: { t: ThemeInfo; accent: string; name: string }) {
  const a = t.accents.find((x) => x.key === accent) ?? t.accents[0];
  const r = Math.min(parseInt(t.tokens.radius, 10) || 12, 22);
  const centred = t.hero === "centered";
  return (
    <svg viewBox="0 0 160 110" aria-hidden="true" focusable="false" className="theme-thumb">
      <rect width="160" height="110" fill={t.tokens.bg} />
      <rect x="10" y="7" width="140" height="14" rx="7" fill={t.tokens.paper} stroke={t.tokens.line} />
      <circle cx="19" cy="14" r="4" fill={a.color} />
      <text x="27" y="17" fontSize="6" fontWeight="700" fill={t.tokens.ink}>
        {name.slice(0, 22)}
      </text>
      <rect x="126" y="10" width="20" height="8" rx="4" fill={a.color} />
      {centred ? (
        <>
          <rect x="34" y="30" width="92" height="9" rx="2" fill={t.tokens.ink} />
          <rect x="52" y="43" width="56" height="4" rx="2" fill={t.tokens.ink2} opacity=".5" />
          {[0, 1, 2].map((i) => (
            <rect key={i} x={18 + i * 46} y={56 + (i === 1 ? 4 : 0)} width="40" height="48" rx="18" fill={t.tokens.soft} />
          ))}
        </>
      ) : (
        <>
          {t.hero === "board" && <rect x="8" y="26" width="144" height="78" rx="6" fill={t.tokens.soft} stroke={t.tokens.ink} strokeWidth="2" />}
          <rect x="16" y="34" width="62" height="8" rx="2" fill={t.tokens.ink} />
          <rect x="16" y="46" width="48" height="8" rx="2" fill={t.tokens.ink} />
          <rect x="16" y="60" width="52" height="3" rx="1.5" fill={t.tokens.ink2} opacity=".5" />
          <rect x="16" y="70" width="30" height="10" rx="5" fill={a.color} />
          <rect x="88" y="34" width="56" height="56" rx={r / 2} fill={t.tokens.soft} />
          <circle cx="116" cy="62" r="12" fill={a.tint} stroke={a.color} strokeWidth="1.5" />
          {t.hero === "ledger" && <rect x="92" y="38" width="48" height="48" rx="3" fill="none" stroke={a.color} strokeDasharray="3 2" />}
        </>
      )}
    </svg>
  );
}

/**
 * The look of the shop. Choosing saves at once (and is logged), then the private preview below reloads. Only keys
 * from the fixed lists are sent: the server refuses anything else.
 */
export function ThemePicker({ biz, onSaved }: { biz: Business; onSaved: (b: Business) => void }) {
  const [list, setList] = useState<ThemeInfo[]>([]);
  const [html, setHtml] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const id = biz.id;
  const current = biz.theme;

  const loadPreview = () => api.preview(id, "home", true).then(setHtml).catch(() => setHtml(null));
  useEffect(() => {
    api.themes().then(setList).catch(() => setList([]));
    loadPreview();
  }, [id]);

  async function choose(theme: string, accent: string) {
    setBusy(true);
    setError("");
    try {
      const b = await api.setTheme(id, theme, accent);
      onSaved(b);
      await loadPreview();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "We couldn't change the look. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function sign(motif: string, art: string) {
    setBusy(true);
    setError("");
    try {
      const b = await api.setSignature(id, motif, art);
      onSaved(b);
      await loadPreview();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "We couldn't change that. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!list.length) return null;
  const active = list.find((t) => t.key === current.key) ?? list[0];
  return (
    <section className="card theme-card" aria-labelledby="theme-h">
      <h3 id="theme-h">The look of your shop</h3>
      <p className="muted small">
        We suggested <strong>{list.find((t) => t.key === current.suggested)?.label}</strong>
        {current.chosen ? "" : " (not saved yet)"}. Pick another and your shop changes at once. Your prices, photos and
        order form stay exactly the same.
      </p>
      <div className="theme-grid" role="radiogroup" aria-label="Shop look">
        {list.map((t) => (
          <button
            type="button"
            key={t.key}
            role="radio"
            aria-checked={t.key === current.key}
            aria-label={`${t.label}. ${t.blurb}`}
            className={"theme-opt" + (t.key === current.key ? " on" : "")}
            disabled={busy}
            onClick={() => choose(t.key, t.key === current.key ? current.accent : "")}
          >
            <Thumb t={t} accent={t.key === current.key ? current.accent : ""} name={biz.name} />
            <strong>{t.label}</strong>
            <small>{t.blurb}</small>
          </button>
        ))}
      </div>
      <div className="accent-row" role="radiogroup" aria-label="Accent colour">
        <span className="muted small">Colour:</span>
        {active.accents.map((a) => (
          <button
            type="button"
            key={a.key}
            role="radio"
            aria-checked={a.key === current.accent}
            className={"accent-opt" + (a.key === current.accent ? " on" : "")}
            disabled={busy}
            onClick={() => choose(active.key, a.key)}
          >
            <span className="swatch" style={{ background: a.color }} aria-hidden="true" />
            {a.label}
          </button>
        ))}
      </div>
      <p className="muted small" style={{ marginTop: 12 }}>
        Your shop's own touch: the little drawings in the top of your page. We picked these from your shop's name; choose
        another any time.
      </p>
      <div className="sig-row" role="radiogroup" aria-label="Drawings">
        {current.motifs.map((m) => (
          <button
            type="button"
            key={m.key}
            role="radio"
            aria-checked={m.key === current.motif}
            aria-label={m.label}
            className={"sig-opt" + (m.key === current.motif ? " on" : "")}
            disabled={busy}
            onClick={() => sign(m.key, "")}
          >
            <span dangerouslySetInnerHTML={{ __html: m.svg }} />
            <small>{m.label}</small>
          </button>
        ))}
      </div>
      <div className="sig-row" role="radiogroup" aria-label="Where the drawings sit">
        {current.arts.map((a) => (
          <button
            type="button"
            key={a.key}
            role="radio"
            aria-checked={a.key === current.art}
            aria-label={a.label}
            className={"sig-opt" + (a.key === current.art ? " on" : "")}
            disabled={busy}
            onClick={() => sign("", a.key)}
          >
            <span dangerouslySetInnerHTML={{ __html: a.svg }} />
            <small>{a.label}</small>
          </button>
        ))}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {html !== null && (
        <>
          <p className="muted small">Private preview of your last saved shop. Only you can see this.</p>
          {/* Same locked-down frame as the full-screen preview: opaque origin, no forms, no top navigation. */}
          <iframe className="theme-preview" title="Live preview of your shop's look" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" srcDoc={html} />
        </>
      )}
    </section>
  );
}
