/** S19: thin drifting light-lines behind the hero, with three small glowing dots travelling along them.
 *  Four static SVG strokes. Performance (hero perf pass): the drift and shimmer animate an HTML wrapper per line, so the
 *  compositor runs them (CSS transforms on an <svg> with % values were re-styled on the main thread every frame), and
 *  the dots are small HTML elements moved along the same curves (computed from LINES[].d) by transform-only Web
 *  Animations (heroLoops.pathLoop)
 *  instead of SMIL, which repainted the whole full-screen SVG every frame. The dots sit in a 1000x560 frame scaled like
 *  the SVG's "slice" (the scale is measured once per resize, never per frame). Everything pauses with the hero card.
  *  Reduced motion, phones and low-power devices (useLiteHero): static lines, no dots. Colours are the hero's own: lime accent and the amber already used by the stack. */
import { useEffect, useRef } from "react";
import { useCalm } from "../motion";
import { curveFromMCS, followHeroPause, pathLoop, useLiteHero } from "./heroLoops";

const LINES = [
  { d: "M-20 330 C 160 240, 300 420, 520 300 S 860 170, 1060 250", c: "rgba(207,122,51,0.34)", w: 1.4, cls: "fl-a" },
  { d: "M-20 380 C 200 300, 340 470, 560 350 S 880 230, 1060 310", c: "rgba(207,122,51,0.2)", w: 1, cls: "fl-b" },
  { d: "M-20 280 C 140 190, 320 360, 500 250 S 840 120, 1060 200", c: "rgba(166,187,52,0.5)", w: 1.4, cls: "fl-c" },
  { d: "M-20 430 C 220 360, 380 500, 600 400 S 900 290, 1060 360", c: "rgba(166,187,52,0.3)", w: 1, cls: "fl-d" },
];
// dur / begin in seconds, as the SMIL dots had them (a negative begin starts the dot part-way along)
const DOTS = [
  { line: 0, dur: 11, begin: 0, r: 5, c: "dc-lime" },
  { line: 2, dur: 14, begin: -5, r: 4, c: "dc-amber" },
  { line: 3, dur: 17, begin: -9, r: 3.5, c: "dc-lime" },
];
const VB_W = 1000;
const VB_H = 560;

export function FlowLines() {
  const reduce = useCalm();
  const lite = useLiteHero();
  const calm = reduce || lite; // reduced motion, or a phone / low-power device: still lines, no dots
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el || calm) return;
    // the SVGs use preserveAspectRatio "xMidYMid slice": scale = max(w/1000, h/560), centred. The dot frame copies it.
    const fit = () => {
      const w = el.clientWidth, h = el.clientHeight;
      if (w && h) el.style.setProperty("--fl-k", String(Math.max(w / VB_W, h / VB_H)));
    };
    fit();
    const ro = "ResizeObserver" in window ? new ResizeObserver(fit) : null;
    ro?.observe(el);
    const anims: Animation[] = [];
    el.querySelectorAll<HTMLElement>(".fl-dot").forEach((dot) => {
      const d = DOTS[Number(dot.dataset.dot)];
      const a = pathLoop(dot, curveFromMCS(LINES[d.line].d), { size: d.r * 6, duration: d.dur * 1000, delay: d.begin * 1000 });
      if (a) anims.push(a);
    });
    const stop = followHeroPause(el, anims);
    return () => {
      ro?.disconnect();
      stop();
    };
  }, [calm]);
  return (
    <div className="flowlines" ref={box} aria-hidden>
      {LINES.map((l, i) => (
        <div key={i} className={`flowline ${calm ? "" : l.cls}`}>
          <svg viewBox={`0 0 ${VB_W} ${VB_H}`} preserveAspectRatio="xMidYMid slice">
            <path d={l.d} fill="none" stroke={l.c} strokeWidth={l.w} strokeLinecap="round" />
          </svg>
          {!calm &&
            DOTS.map((d, k) =>
              d.line === i ? (
                <div key={k} className="fl-frame">
                  <i className={`fl-dot ${d.c}`} data-dot={k} style={{ width: d.r * 6, height: d.r * 6 }} />
                </div>
              ) : null,
            )}
        </div>
      ))}
    </div>
  );
}
