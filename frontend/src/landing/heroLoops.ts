import { useEffect, useState } from "react";
/** Hero loops that run on the compositor, and one pause switch for all of them.
 *  - pathLoop: a small HTML element travels along a curve at constant speed. The curve is sampled once in plain JS
 *    (no DOM reads: SVG getPointAtLength forced a layout and re-walked the path on every call) and played as a
 *    transform-only Web Animation, which the compositor runs. (SMIL animateMotion repainted the whole SVG every
 *    frame; CSS offset-path animations restyle on the main thread.)
 *  - The hero card carries data-paused="1" while it is off screen or fully covered by the dark panel (set in Landing).
 *    CSS loops pause through that attribute; Web Animations listen for HERO_PAUSE on the card. */
export const HERO_PAUSE = "lw-hero-pause";

type Pt = [number, number];
type Curve = (u: number) => Pt; // u in [0, 1] along the curve (not yet by length)

const cubic = (a: Pt, b: Pt, c: Pt, d: Pt): Curve => (t) => {
  const s = 1 - t;
  const k0 = s * s * s, k1 = 3 * s * s * t, k2 = 3 * s * t * t, k3 = t * t * t;
  return [k0 * a[0] + k1 * b[0] + k2 * c[0] + k3 * d[0], k0 * a[1] + k1 * b[1] + k2 * c[1] + k3 * d[1]];
};

/** "M x y C x y, x y, x y S x y, x y" (the hero's light-lines) as a curve. The S control point mirrors the C's last. */
export function curveFromMCS(d: string): Curve {
  const n = (d.match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
  if (n.length !== 12) throw new Error("expected M C S path");
  const p0: Pt = [n[0], n[1]], c1: Pt = [n[2], n[3]], c2: Pt = [n[4], n[5]], p1: Pt = [n[6], n[7]];
  const r: Pt = [2 * p1[0] - c2[0], 2 * p1[1] - c2[1]], c3: Pt = [n[8], n[9]], p2: Pt = [n[10], n[11]];
  const a = cubic(p0, c1, c2, p1), b = cubic(p1, r, c3, p2);
  return (u) => (u < 0.5 ? a(u * 2) : b(u * 2 - 1));
}

/** An ellipse travelled from its leftmost point through the bottom (the near side), right, top and back, like the
 *  SVG path "M(cx-rx) cy a rx ry 0 1 0 2rx 0 a rx ry 0 1 0 -2rx 0". */
export const ellipseFromLeft = (cx: number, cy: number, rx: number, ry: number): Curve => (u) => {
  const t = Math.PI - 2 * Math.PI * u;
  return [cx + rx * Math.cos(t), cy + ry * Math.sin(t)];
};

/** n+1 points at equal distances along the curve (constant speed, like SMIL's paced motion). */
function byLength(curve: Curve, n: number): Pt[] {
  const fine = 2000;
  const pts: Pt[] = [];
  const len: number[] = [0];
  for (let i = 0; i <= fine; i++) {
    pts.push(curve(i / fine));
    if (i) len.push(len[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  }
  const total = len[fine];
  const out: Pt[] = [];
  let j = 0;
  for (let k = 0; k <= n; k++) {
    const want = (total * k) / n;
    while (j < fine - 1 && len[j + 1] < want) j++;
    const seg = len[j + 1] - len[j] || 1;
    const f = Math.min(1, Math.max(0, (want - len[j]) / seg));
    out.push([pts[j][0] + (pts[j + 1][0] - pts[j][0]) * f, pts[j][1] + (pts[j + 1][1] - pts[j][1]) * f]);
  }
  return out;
}

export function pathLoop(
  el: HTMLElement,
  curve: Curve,
  opts: { size: number; duration: number; delay?: number; points?: number; scaleAt?: (t: number) => number },
): Animation | null {
  if (typeof el.animate !== "function") return null;
  const n = opts.points ?? 64;
  const h = opts.size / 2;
  const frames: Keyframe[] = byLength(curve, n).map(([x, y], i) => {
    const s = opts.scaleAt ? ` scale(${opts.scaleAt(i / n).toFixed(4)})` : "";
    return { transform: `translate(${(x - h).toFixed(2)}px, ${(y - h).toFixed(2)}px)${s}` };
  });
  return el.animate(frames, { duration: opts.duration, delay: opts.delay ?? 0, iterations: Infinity, easing: "linear" });
}

/** Pauses/plays `anims` with the hero card that contains `el`. Returns a cleanup function. */
export function followHeroPause(el: Element, anims: Animation[]): () => void {
  const card = el.closest<HTMLElement>(".hero-card");
  if (!card || !anims.length) return () => anims.forEach((a) => a.cancel());
  const set = (paused: boolean) => anims.forEach((a) => (paused ? a.pause() : a.play()));
  const on = (e: Event) => set(!!(e as CustomEvent<boolean>).detail);
  if (card.dataset.paused === "1") set(true);
  card.addEventListener(HERO_PAUSE, on);
  return () => {
    card.removeEventListener(HERO_PAUSE, on);
    anims.forEach((a) => a.cancel());
  };
}

/** Phones and low-power devices get a lighter hero (still light-lines, no scroll spread of the stack): narrow screens,
 *  4 or fewer CPU cores, or Save-Data. Measured: those effects cost a phone more per scroll frame than they are worth. */
const LITE_QUERY = "(max-width: 899px)";
function isLite(): boolean {
  if (typeof window === "undefined") return false;
  const nav = navigator as Navigator & { connection?: { saveData?: boolean } };
  return (
    window.matchMedia(LITE_QUERY).matches ||
    (typeof nav.hardwareConcurrency === "number" && nav.hardwareConcurrency > 0 && nav.hardwareConcurrency <= 4) ||
    !!nav.connection?.saveData
  );
}
export function useLiteHero(): boolean {
  const [lite, setLite] = useState(isLite);
  useEffect(() => {
    const mq = window.matchMedia(LITE_QUERY);
    const f = () => setLite(isLite());
    mq.addEventListener?.("change", f);
    return () => mq.removeEventListener?.("change", f);
  }, []);
  return lite;
}
