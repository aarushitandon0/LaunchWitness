/** S19: the rounded top edge of a dark panel. It flattens (scaleY, transform only) as the panel reaches the top, so
 *  the panel reads as sliding up over the one before it. Decorative; hidden from assistive tech; static with reduced motion. */
import { motion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";
import { useCalm } from "../motion";

export function PanelCap() {
  const calm = useCalm();
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "start 0.3"] });
  const sy = useTransform(scrollYProgress, [0, 1], [1, calm ? 1 : 0.12]);
  return <motion.div ref={ref} className="panel-cap" style={{ scaleY: sy }} aria-hidden />;
}
