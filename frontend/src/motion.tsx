import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

/** Same curves as the CSS tokens (--ease, --ease-in-out). Calm, never bouncy. */
export const EASE = [0.22, 1, 0.36, 1] as const;
export const EASE_IN_OUT = [0.65, 0, 0.35, 1] as const;

/** True when the visitor asked for less motion (OS setting). */
export const useCalm = () => !!useReducedMotion();

/** A round status mark whose tick draws itself. */
export function Tick({ size = 22, animate = true }: { size?: number; animate?: boolean }) {
  const calm = useCalm();
  const draw = animate && !calm;
  return (
    <svg className="mark mark-ok" width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <motion.circle
        cx="12"
        cy="12"
        r="11"
        initial={draw ? { scale: 0.6, opacity: 0 } : false}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.35, ease: EASE }}
        style={{ transformOrigin: "12px 12px" }}
      />
      <motion.path
        d="M7 12.5l3.2 3.2L17 9"
        initial={draw ? { pathLength: 0 } : false}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.4, delay: draw ? 0.15 : 0, ease: EASE }}
      />
    </svg>
  );
}

export function Cross({ size = 22, tone = "bad" }: { size?: number; tone?: "bad" | "wait" }) {
  const calm = useCalm();
  return (
    <motion.svg
      className={`mark mark-${tone}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden
      initial={calm ? false : { scale: 0.6, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.3, ease: EASE }}
    >
      <circle cx="12" cy="12" r="11" />
      <path d="M12 7v6.5M12 16.6v.4" />
    </motion.svg>
  );
}

export function Spinner({ size = 22 }: { size?: number }) {
  return (
    <svg className="mark mark-spin" width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="9.5" />
    </svg>
  );
}

export function Dot({ size = 22 }: { size?: number }) {
  return (
    <svg className="mark mark-idle" width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="5" />
    </svg>
  );
}

/** Types `text` in, character by character. Calls onDone when finished. Instant with reduced motion. */
export function TypeIn({ text, onDone, speed = 16 }: { text: string; onDone?: () => void; speed?: number }) {
  const calm = useCalm();
  const [n, setN] = useState(calm ? text.length : 0);
  useEffect(() => {
    if (calm) {
      setN(text.length);
      onDone?.();
      return;
    }
    setN(0);
    const t = window.setInterval(() => {
      setN((v) => {
        if (v >= text.length) {
          window.clearInterval(t);
          return v;
        }
        return v + 1;
      });
    }, speed);
    return () => window.clearInterval(t);
  }, [text, calm]);
  useEffect(() => {
    if (!calm && n >= text.length && text.length > 0) onDone?.();
  }, [n >= text.length]);
  return (
    <span className="typein">
      <span aria-hidden>{text.slice(0, n)}</span>
      {n < text.length && <span className="caret" aria-hidden />}
      {/* screen readers get the whole sentence at once */}
      <span className="sr-only">{text}</span>
    </span>
  );
}
