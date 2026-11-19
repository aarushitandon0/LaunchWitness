/** S19: "Our promises" as a list with one bright item and a lime beam + small burst pointing at it.
 *  The active item follows the pointer (hover) and the scroll (the row nearest the middle of the screen).
 *  Rows are equal height, so the beam is one element moved with a transform. Phones (and reduced motion) get the
 *  plain list with the active row highlighted and no beam. Turn off the beam: .promise-beam { display: none }. */
import { motion, useInView } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { EASE, useCalm } from "../motion";

const SPARKS = Array.from({ length: 9 }, (_, i) => {
  const a = (i / 9) * Math.PI * 2;
  return { x: Math.cos(a) * (26 + (i % 3) * 8), y: Math.sin(a) * (26 + (i % 3) * 8) };
});

export function PromiseBeam({ items }: { items: string[][] }) {
  const calm = useCalm();
  const [active, setActive] = useState(0);
  const [wide, setWide] = useState(false);
  const list = useRef<HTMLUListElement>(null);
  const seen = useInView(list, { once: true, amount: 0.3 });
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 900px)");
    const f = () => setWide(mq.matches);
    f();
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);
  // the row nearest the middle of the screen is the active one
  useEffect(() => {
    const el = list.current;
    if (!el || !("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && setActive(Number((e.target as HTMLElement).dataset.i))),
      { rootMargin: "-42% 0px -42% 0px" },
    );
    el.querySelectorAll("li").forEach((li) => io.observe(li));
    return () => io.disconnect();
  }, []);
  const beam = wide && !calm;
  return (
    <div className="promise-stage" data-beam={beam ? "1" : "0"}>
      <ul className="promise-list" ref={list}>
        {items.map(([title, text], i) => (
          <li
            key={title}
            data-i={i}
            className={`promise${active === i ? " is-active" : ""}`}
            onMouseEnter={() => setActive(i)}
          >
            <div className="title">{title}</div>
            <p>{text}</p>
          </li>
        ))}
      </ul>
      {beam && (
        <div className="promise-beam" aria-hidden>
          <motion.div
            className="beam-row"
            animate={{ y: `${active * 100}%`, opacity: seen ? 1 : 0 }}
            transition={{ type: "spring", stiffness: 140, damping: 22 }}
            style={{ height: `${100 / items.length}%` }}
          >
            <span className="beam-line" />
            <span className="beam-orb" />
            <motion.span
              key={active}
              className="beam-sparks"
              initial="a"
              animate="b"
            >
              {SPARKS.map((s, k) => (
                <motion.i
                  key={k}
                  variants={{ a: { x: 0, y: 0, opacity: 0.9, scale: 1 }, b: { x: s.x, y: s.y, opacity: 0, scale: 0.4 } }}
                  transition={{ duration: 0.9, ease: EASE }}
                />
              ))}
            </motion.span>
          </motion.div>
        </div>
      )}
    </div>
  );
}
