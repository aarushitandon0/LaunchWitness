/** S19: decode / scramble reveal for headings, and a word-by-word fade for paragraphs.
 *  Accessibility: the real text is always in the DOM and never changes. The scramble is a CSS ::after layer that
 *  reads `data-s` (pseudo-element content is not in textContent or the accessibility tree), so a screen reader gets
 *  the real sentence from the first frame. Reduced motion: nothing runs. Turn off: set DECODE_ON to false. */
import { motion, useInView } from "framer-motion";
import { Children, ReactNode, useEffect, useRef, useState } from "react";
import { EASE, useCalm } from "../motion";

export const DECODE_ON = true;
const GLYPHS = "abcdefghijkmnopqrstuvwxyzACEFGHKMNRSTUVXYZ0123456789#%&*+/<>=";

function scramble(text: string, settled: number): string {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    out += i < settled || c === " " ? c : GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
  }
  return out;
}

/** Letters settle left to right over `ms`. `now` starts it at once (hero); otherwise it waits to enter the screen (once). */
export function DecodeText({ text, delay = 0, ms = 800, now = false }: { text: string; delay?: number; ms?: number; now?: boolean }) {
  const calm = useCalm();
  const ref = useRef<HTMLSpanElement>(null);
  const seen = useInView(ref, { once: true, amount: 0.6 });
  const go = now || seen;
  const off = calm || !DECODE_ON;
  const [shown, setShown] = useState<string | null>(off ? null : scramble(text, 0)); // null = finished / not running
  useEffect(() => {
    if (off || !go) return;
    let raf = 0;
    let last = 0;
    const t0 = performance.now() + delay;
    const tick = (t: number) => {
      const k = (t - t0) / ms;
      if (k >= 1) return setShown(null);
      if (k >= 0 && t - last > 42) {
        last = t;
        setShown(scramble(text, Math.floor(k * k * (3 - 2 * k) * text.length)));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [go, off, text, delay, ms]);
  const running = shown !== null;
  return (
    <span ref={ref} className={running ? "dt dt-run" : "dt"} data-s={running ? shown : undefined}>
      {text}
    </span>
  );
}

/** A paragraph whose words fade in one after another. The words stay ordinary text separated by real spaces. */
export function WordFade({ children, delay = 0, step = 0.028, now = false }: { children: ReactNode; delay?: number; step?: number; now?: boolean }) {
  const calm = useCalm();
  const ref = useRef<HTMLSpanElement>(null);
  const seen = useInView(ref, { once: true, amount: 0.4 });
  const text = Children.toArray(children).join("");
  if (calm) return <>{text}</>;
  const words = text.split(" ");
  const go = now || seen;
  return (
    <span ref={ref}>
      {words.map((w, i) => (
        <span key={i}>
          <motion.span
            style={{ display: "inline-block" }}
            initial={{ opacity: 0 }}
            animate={go ? { opacity: 1 } : undefined}
            transition={{ duration: 0.5, delay: delay + Math.min(i * step, 1.1), ease: EASE }}
          >
            {w}
          </motion.span>
          {i < words.length - 1 ? " " : ""}
        </span>
      ))}
    </span>
  );
}
