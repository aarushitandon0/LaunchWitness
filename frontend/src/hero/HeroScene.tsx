import { MotionValue, useMotionValueEvent } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import still from "./still.webp";

/** Same order as scene.ts HOP_NAMES (kept here so this file never imports three). */
const HOPS = ["Address", "Secure page", "Your shop", "Order form", "Mail server", "Your inbox"];
const LABEL = `The proof, bottom to top: ${HOPS.join(", ")}. A light carries a test order up the layers and each one lights when it passes; at the top the check mark lights up.`;

/** A real GPU only. Software WebGL (SwiftShader, llvmpipe, …) would draw this scene on the CPU and starve the page,
 * so those browsers keep the still image. `failIfMajorPerformanceCaveat` refuses most of them; the name check is
 * the backstop. */
function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    const gl = (c.getContext("webgl2", { failIfMajorPerformanceCaveat: true }) ||
      c.getContext("webgl", { failIfMajorPerformanceCaveat: true })) as WebGLRenderingContext | null;
    if (!gl) return false;
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    const name = String(info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return !/swiftshader|llvmpipe|software|softpipe|microsoft basic render/i.test(name);
  } catch {
    return false;
  }
}

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

type Scene = { setSpread: (v: number) => void; dispose: () => void; stillDataUrl: () => string };

/**
 * The hero scene. First paint shows the still image; then (not for reduced motion, and only with WebGL) three.js is
 * loaded with a dynamic import and the live scene fades in over it. `?hero-still` renders the still frame and exposes
 * it as `window.__lwHeroStill` (used once to make still.webp: see e2e/screens).
 */
export function HeroScene({ progress }: { progress: MotionValue<number> }) {
  const host = useRef<HTMLDivElement>(null);
  const labels = useRef<(HTMLSpanElement | null)[]>([]);
  const scene = useRef<Scene | null>(null);
  const [live, setLive] = useState(false);

  useMotionValueEvent(progress, "change", (v) => scene.current?.setSpread(v));

  useEffect(() => {
    const makeStill = new URLSearchParams(window.location.search).has("hero-still");
    if (!makeStill && (reducedMotion() || !webglAvailable())) return; // the still image stays
    let cancelled = false;
    const go = () =>
      import("./scene")
        .then(({ createHeroScene }) => {
          if (cancelled || !host.current) return;
          const el = host.current;
          // the card's visible area, in the scene box's coordinates (the box bleeds past the card on purpose)
          const visible = () => {
            const card = el.closest(".hero-card")?.getBoundingClientRect();
            const box = el.getBoundingClientRect();
            return card ? { right: card.right - box.left, bottom: card.bottom - box.top } : { right: box.width, bottom: box.height };
          };
          const s = createHeroScene(el, labels.current.filter(Boolean) as HTMLElement[], { still: makeStill, visible });
          scene.current = s;
          if (makeStill) (window as unknown as { __lwHeroStill: string }).__lwHeroStill = s.stillDataUrl();
          requestAnimationFrame(() => !cancelled && setLive(true));
        })
        .catch(() => undefined); // no scene: the still image stays
    // after first paint, when the browser has a moment
    const idle = (window as unknown as { requestIdleCallback?: (f: () => void, o?: object) => number }).requestIdleCallback;
    const id = idle ? idle(go, { timeout: 1200 }) : window.setTimeout(go, 300);
    return () => {
      cancelled = true;
      if (!idle) window.clearTimeout(id);
      scene.current?.dispose();
      scene.current = null;
    };
  }, []);

  return (
    <div className={`hero-scene${live ? " is-live" : ""}`} role="img" aria-label={LABEL}>
      <div className="hero-still" aria-hidden>
        <img src={still} alt="" decoding="async" />
      </div>
      <div className="hero-canvas" ref={host} aria-hidden />
      <div className="hero-labels" aria-hidden>
        {HOPS.map((h, i) => (
          <span key={h} className="hero-label" ref={(el) => (labels.current[i] = el)}>
            {h}
          </span>
        ))}
      </div>
    </div>
  );
}
