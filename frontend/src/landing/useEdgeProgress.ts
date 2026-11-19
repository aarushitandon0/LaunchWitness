/** Scroll progress of an element's top edge through the viewport, as a framer-motion value (no React renders).
 *  0 when the element's top is at `from` x viewport height, 1 when it reaches `to` x viewport height, clamped.
 *  Same numbers as useScroll({ target, offset: ["start <from>", "start <to>"] }), but cheaper: framer's version
 *  re-measured the target (offsetTop chain, scrollHeight) on every scroll event, forcing a layout each frame.
 *  Here the element's page position is measured once, and again only when the page or window changes size;
 *  a scroll reads window.scrollY once per frame, in framer's read phase (before any style writes that frame), so the
 *  read never forces a style or layout pass. */
import { cancelFrame, frame, MotionValue, useMotionValue } from "framer-motion";
import { RefObject, useEffect } from "react";

export function useEdgeProgress(ref: RefObject<HTMLElement>, from = 1, to = 0): MotionValue<number> {
  const mv = useMotionValue(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let top = 0;
    let vh = 1;
    const update = () => {
      const a = top - vh * from;
      const b = top - vh * to;
      const v = b === a ? 1 : (window.scrollY - a) / (b - a);
      mv.set(v < 0 ? 0 : v > 1 ? 1 : v);
    };
    const measure = () => {
      top = el.getBoundingClientRect().top + window.scrollY;
      vh = document.documentElement.clientHeight || window.innerHeight;
      update();
    };
    measure();
    let queued = false;
    const read = () => {
      queued = false;
      update();
    };
    const onScroll = () => {
      if (queued) return;
      queued = true;
      frame.read(read);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", measure, { passive: true });
    const ro = "ResizeObserver" in window ? new ResizeObserver(measure) : null;
    ro?.observe(document.body);
    return () => {
      cancelFrame(read);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", measure);
      ro?.disconnect();
    };
  }, [ref, mv, from, to]);
  return mv;
}
