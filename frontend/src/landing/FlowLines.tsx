/** S19: thin drifting light-lines behind the hero, with three small glowing dots travelling along them.
 *  Four SVG strokes only. Each line is its own composited layer that drifts with transform/opacity keyframes; the
 *  dots use SMIL (animateMotion). Everything pauses when the hero is off screen. Reduced motion: static lines, no dots.
 *  Colours are the hero's own: lime accent and the amber already used by the stack. */
import { useEffect, useRef } from "react";
import { useCalm } from "../motion";

const LINES = [
  { d: "M-20 330 C 160 240, 300 420, 520 300 S 860 170, 1060 250", c: "rgba(207,122,51,0.34)", w: 1.4, cls: "fl-a" },
  { d: "M-20 380 C 200 300, 340 470, 560 350 S 880 230, 1060 310", c: "rgba(207,122,51,0.2)", w: 1, cls: "fl-b" },
  { d: "M-20 280 C 140 190, 320 360, 500 250 S 840 120, 1060 200", c: "rgba(166,187,52,0.5)", w: 1.4, cls: "fl-c" },
  { d: "M-20 430 C 220 360, 380 500, 600 400 S 900 290, 1060 360", c: "rgba(166,187,52,0.3)", w: 1, cls: "fl-d" },
];
const DOTS = [
  { line: 0, dur: "11s", begin: "0s", r: 5, c: "dc-lime" },
  { line: 2, dur: "14s", begin: "-5s", r: 4, c: "dc-amber" },
  { line: 3, dur: "17s", begin: "-9s", r: 3.5, c: "dc-lime" },
];

export function FlowLines() {
  const calm = useCalm();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (!el || calm || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(([e]) => {
      el.dataset.paused = e.isIntersecting ? "0" : "1";
      el.querySelectorAll("svg").forEach((s) => (e.isIntersecting ? s.unpauseAnimations?.() : s.pauseAnimations?.()));
    });
    io.observe(el);
    return () => io.disconnect();
  }, [calm]);
  return (
    <div className="flowlines" ref={box} aria-hidden>
      {LINES.map((l, i) => (
        <svg key={i} className={`flowline ${calm ? "" : l.cls}`} viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid slice">
          <defs>
            <radialGradient id={`fl-lime-${i}`}>
              <stop offset="0" stopColor="#fbffd9" stopOpacity="0.95" />
              <stop offset="0.35" stopColor="#dcf06a" stopOpacity="0.7" />
              <stop offset="1" stopColor="#dcf06a" stopOpacity="0" />
            </radialGradient>
            <radialGradient id={`fl-amber-${i}`}>
              <stop offset="0" stopColor="#ffe7d1" stopOpacity="0.95" />
              <stop offset="0.35" stopColor="#f09a50" stopOpacity="0.65" />
              <stop offset="1" stopColor="#f09a50" stopOpacity="0" />
            </radialGradient>
          </defs>
          <path id={`fl-p-${i}`} d={l.d} fill="none" stroke={l.c} strokeWidth={l.w} strokeLinecap="round" />
          {!calm &&
            DOTS.filter((d) => d.line === i).map((d, k) => (
              <circle key={k} r={d.r * 3} fill={`url(#fl-${d.c === "dc-lime" ? "lime" : "amber"}-${i})`}>
                <animateMotion dur={d.dur} begin={d.begin} repeatCount="indefinite" rotate="0">
                  <mpath href={`#fl-p-${i}`} />
                </animateMotion>
              </circle>
            ))}
        </svg>
      ))}
    </div>
  );
}
