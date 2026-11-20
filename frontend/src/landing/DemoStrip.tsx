import { useEffect, useRef, useState } from "react";
import { useCalm } from "../motion";
import "./demo-strip.css";
import { DEMO_SHOPS, LAPTOP_H, LAPTOP_MIN, LAPTOP_W, laptopThumb, THUMB_H, THUMB_W } from "./demoShops";

/** S21: "See shops made with LaunchWitness": a row of cards, one per demo shop (S21B: laptop-shaped from 1024 px,
 * phone-shaped below).
 *
 * It is a normal horizontal scroller (swipe, drag with a trackpad, scroll-snap, arrow buttons, Tab through the links).
 * While nobody is touching it, it drifts slowly to the left like a marquee: the row's scroll position moves (composited,
 * no layout or paint of the cards), the list is drawn twice so it loops without a jump, and the copy is hidden from
 * screen readers and the keyboard. The drift stops while the pointer is over it, while anything in it has focus, for a
 * few seconds after a touch / wheel / arrow, while it is off screen or the tab is hidden, and never starts with
 * reduced motion (then it is just the scrollable row). */
const SPEED = 22; // px per second
const RESUME_MS = 3500;

export function DemoStrip() {
  const calm = useCalm();
  const row = useRef<HTMLDivElement>(null);
  const [auto, setAuto] = useState(!calm);
  const hold = useRef({ hover: false, focus: false, until: 0 });

  useEffect(() => {
    setAuto(!calm);
  }, [calm]);

  useEffect(() => {
    const el = row.current;
    if (!el || !auto) return;
    let raf = 0;
    let last = 0;
    let carry = 0;
    const tick = (t: number) => {
      raf = requestAnimationFrame(tick);
      const dt = last ? Math.min(t - last, 64) : 0;
      last = t;
      const h = hold.current;
      if (h.hover || h.focus || document.hidden || Date.now() < h.until) {
        el.classList.remove("drifting");
        return;
      }
      el.classList.add("drifting");
      carry += (SPEED * dt) / 1000;
      const step = Math.floor(carry);
      if (!step) return;
      carry -= step;
      const half = el.scrollWidth / 2;
      el.scrollLeft = el.scrollLeft + step >= half ? el.scrollLeft + step - half : el.scrollLeft + step;
    };
    // The frame loop runs ONLY while the strip is on screen: off screen it costs nothing (the hero stays as fast as before).
    const start = () => {
      if (!raf) {
        last = 0;
        raf = requestAnimationFrame(tick);
      }
    };
    const stop = () => {
      cancelAnimationFrame(raf);
      raf = 0;
      el.classList.remove("drifting");
    };
    const io = new IntersectionObserver(([e]) => (e.isIntersecting ? start() : stop()));
    io.observe(el);
    return () => {
      stop();
      io.disconnect();
    };
  }, [auto]);

  const pause = () => {
    hold.current.until = Date.now() + RESUME_MS;
  };
  const by = (dir: number) => {
    const el = row.current;
    if (!el) return;
    pause();
    const card = el.querySelector<HTMLElement>(".demo-card");
    el.scrollBy({ left: dir * (card ? card.offsetWidth + 16 : 240) * 2, behavior: calm ? "auto" : "smooth" });
  };

  const cards = (copy: boolean) =>
    DEMO_SHOPS.map((d) => (
      <li key={`${copy ? "c" : ""}${d.slug}`} aria-hidden={copy || undefined}>
        <a
          className="demo-card"
          href={`/demo/${d.slug}`}
          target="_blank"
          rel="noopener"
          tabIndex={copy ? -1 : undefined}
          aria-label={copy ? undefined : `${d.name}, ${d.look} demo shop (opens in a new tab)`}
        >
          {/* S21B: a laptop frame with the 1440-wide page on a laptop, a phone frame with the 390 page below LAPTOP_MIN. */}
          <span className="demo-device">
            <picture>
              <source media={`(min-width: ${LAPTOP_MIN}px)`} srcSet={laptopThumb(d)} width={LAPTOP_W} height={LAPTOP_H} />
              <img src={d.thumb} width={THUMB_W} height={THUMB_H} alt={copy ? "" : d.name} loading="lazy" decoding="async" />
            </picture>
          </span>
          <span className="demo-name">{d.name}</span>
          <span className="demo-look">{d.look}</span>
        </a>
      </li>
    ));

  return (
    <div className="demo-strip">
      <div
        ref={row}
        className="demo-row"
        onPointerEnter={(e) => {
          if (e.pointerType === "mouse") hold.current.hover = true;
        }}
        onPointerLeave={() => {
          hold.current.hover = false;
        }}
        onPointerDown={pause}
        onTouchStart={pause}
        onWheel={pause}
        onFocus={() => {
          hold.current.focus = true;
        }}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node)) hold.current.focus = false;
        }}
      >
        <ul className="demo-list">
          {cards(false)}
          {auto && cards(true)}
        </ul>
      </div>
      <div className="demo-arrows">
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Scroll the demo shops left" onClick={() => by(-1)}>
          ←
        </button>
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Scroll the demo shops right" onClick={() => by(1)}>
          →
        </button>
      </div>
    </div>
  );
}
