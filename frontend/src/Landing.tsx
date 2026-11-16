import { motion, MotionValue, useScroll, useSpring, useTransform } from "framer-motion";
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { AddressResult, api, ApiError } from "./api";
import { ErrorBox } from "./Describe";
import { EASE, useCalm } from "./motion";

const STEPS: { title: string; text: string; icon: ReactNode }[] = [
  {
    title: "Describe your business",
    text: "Write a few lines about what you sell and paste your price list, the way you'd tell a friend. A photo of your menu works too.",
    icon: (
      <svg viewBox="0 0 64 64" className="step-icon" aria-hidden>
        <rect x="8" y="12" width="48" height="34" rx="10" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M20 46l-6 9 14-9" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M18 25h28M18 33h18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    title: "Launch it on GoDaddy",
    text: "We turn it into your shop. Check the details, then approve the launch: you see every change and the exact cost before anything happens.",
    icon: (
      <svg viewBox="0 0 64 64" className="step-icon" aria-hidden>
        <rect x="8" y="10" width="48" height="40" rx="8" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M8 20h48" stroke="currentColor" strokeWidth="1.6" />
        <circle cx="14" cy="15" r="1.6" fill="currentColor" />
        <circle cx="19" cy="15" r="1.6" fill="currentColor" />
        <rect x="15" y="27" width="14" height="14" rx="3" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M35 29h14M35 35h10M35 41h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    title: "Prove a real order reaches you",
    text: "A real test order goes through your shop's own order form, hop by hop: the address, the secure padlock, the form, the mail server, your inbox.",
    icon: (
      <svg viewBox="0 0 64 64" className="step-icon" aria-hidden>
        <rect x="12" y="8" width="40" height="48" rx="8" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M20 22h24M20 30h16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="40" cy="44" r="8" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M36.5 44.2l2.4 2.4 4.6-4.8" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    title: "Keep checking and fixing",
    text: "After launch we keep checking quietly. If something breaks we explain it in plain words, repair it when a safe fix exists, and tell you.",
    icon: (
      <svg viewBox="0 0 64 64" className="step-icon" aria-hidden>
        <path d="M32 7l20 7v15c0 13-8.5 23-20 28C20.5 52 12 42 12 29V14z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M23.5 31.5l6 6 11-12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

const PIECES = [
  ["Domains", "A free shop address now; your own name, found and priced, in practice"],
  ["DNS", "Every setting backed up before it changes"],
  ["Email", "Order emails from our mailbox, with its anti-spam settings checked daily"],
  ["VPS", "Your shop served from a GoDaddy server"],
  ["HTTPS", "A secure padlock, checked for real"],
  ["Monitoring", "Quiet checks every 15 minutes after launch"],
];

const WHO: { id: string; title: string; text: string; demos: [string, string][] }[] = [
  {
    id: "who-food",
    title: "Home food",
    text: "Cakes, tiffin, pickles and snacks, made in your kitchen and ordered ahead.",
    demos: [["/demo/meera", "a home baker"], ["/demo/sunita", "a tiffin service"]],
  },
  {
    id: "who-handmade",
    title: "Handmade goods",
    text: "Candles, crafts, jewellery and gift hampers, made in small batches.",
    demos: [],
  },
  {
    id: "who-custom",
    title: "Custom work",
    text: "Tailoring, embroidery and art commissions, made to each customer's order.",
    demos: [["/demo/imran", "a tailor"]],
  },
];

/** The proof, hop by hop: the same six hops as the hero's layers (bottom to top). */
export const HOPS: { name: string; text: string }[] = [
  { name: "Address", text: "Your shop's address leads to our GoDaddy server." },
  { name: "Secure page", text: "It opens securely, with a valid padlock." },
  { name: "Your shop", text: "The page that opens is really your shop: we look for its own hidden marker." },
  { name: "Order form", text: "A real test order goes in through your shop's own order form, like a customer's." },
  { name: "Mail server", text: "The mail server accepts the order email for you." },
  { name: "Your inbox", text: "It reaches you: you tap “Yes, I got it” in that email." },
];

/** What runs after launch. Matches monitor/scheduler.py (QUICK_MINUTES, daily jobs, RECHECK_SECONDS) and
 * renewals.py (THRESHOLDS 30/7/1, CERT_THRESHOLDS 7/1). Change both together. */
const WATCH: { when: string; title: string; text: string }[] = [
  {
    when: "Every 15 minutes",
    title: "Your shop opens",
    text: "Your address still leads to your shop, and it opens securely.",
  },
  {
    when: "Every day",
    title: "The whole order path",
    text:
      "Everything above, plus: the settings that keep order emails out of spam are still there, nothing we set at " +
      "launch has changed, and a real test order goes through your order form. The daily run proves your form took " +
      "the order and the mail server accepted it. That it reached your inbox is proven at launch, and again whenever " +
      "you tap “Yes, I got it”.",
  },
  {
    when: "Before things run out",
    title: "Renewals",
    text:
      "The padlock renews itself for free; if it hasn't with 7 days left, you hear from us (and again at 1 day). " +
      "Your shop's address and our order mailbox are renewed by our team, who are warned 30, 7 and 1 days ahead. " +
      "We never renew or pay for anything by ourselves.",
  },
  {
    when: "When something breaks",
    title: "Check, fix, tell you",
    text:
      "We check again a minute later, to rule out a blip. If it's still broken, the Doctor works out what broke and " +
      "applies a safe fix if one is allowed; otherwise your report says exactly what to do. Then we check again; " +
      "if it's still broken, we email you once about that problem. Money is never spent without you.",
  },
];

const PROMISES = [
  ["Nothing is bought without your approval", "You see the exact price first. Buying is switched off unless you approve it."],
  ["You see every change before it happens", "Each setting is shown as before and after, in plain words."],
  ["A backup first, and an undo", "We save a copy of your settings before changing anything, so a failed launch can be put back."],
];

export default function Landing() {
  const calm = useCalm();
  const darkRef = useRef<HTMLElement>(null);
  // 0 → the dark section's top is at the bottom of the screen; 1 → it reached the top.
  const { scrollYProgress } = useScroll({ target: darkRef, offset: ["start end", "start start"] });
  const p = useSpring(scrollYProgress, { stiffness: 140, damping: 30, mass: 0.4, restDelta: 0.0005 });
  const scale = useTransform(p, [0, 1], [1, calm ? 1 : 0.88]);
  const y = useTransform(p, [0, 1], [0, calm ? 0 : -36]);
  const dim = useTransform(p, [0, 1], [0, calm ? 0 : 0.55]);
  useEffect(() => {
    const h = window.location.hash;
    if (h.length > 1 && !h.startsWith("#/")) {
      const t = window.setTimeout(() => document.getElementById(h.slice(1))?.scrollIntoView({ block: "start" }), 120);
      return () => window.clearTimeout(t);
    }
  }, []);

  return (
    <div className="landing">
      <div className="stack">
        <motion.section className="hero-card" style={{ scale, y }} aria-labelledby="hero-title">
          <div className="hero-inner">
            <div className="hero-head">
              <motion.p
                className="eyebrow"
                initial={calm ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, ease: EASE }}
              >
                For small sellers · runs on GoDaddy
              </motion.p>
              <h1 className="display" id="hero-title">
                <Line i={0}>Is your shop</Line>
                <Line i={1}>
                  <span className="inline-icon" aria-hidden>
                    <svg viewBox="0 0 24 24">
                      <path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="var(--accent-ink)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                  actually ready
                </Line>
                <Line i={2}>for customers?</Line>
              </h1>
            </div>
            <HeroShape progress={p} />
            <motion.div
              className="hero-copy"
              initial={calm ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.45, ease: EASE }}
            >
              <p>
                Describe your business. LaunchWitness puts it online on GoDaddy, proves a real order reaches you, fixes
                what breaks, and keeps checking.
              </p>
              <div className="hero-meta">
                <a className="btn btn-primary" href="#/new">
                  Start
                </a>
                <a className="dotlink" href="/demo/meera">
                  See a demo shop
                </a>
              </div>
              <p className="small">
                Just looking? <a href="#/try">Try it without an account</a>, in practice mode: nothing is bought and
                nothing goes on the internet.
              </p>
            </motion.div>
          </div>
          <motion.div className="hero-dim" style={{ opacity: dim }} aria-hidden />
          <div className="scroll-cue" aria-hidden>
            Scroll <span />
          </div>
        </motion.section>

        <section className="dark on-dark" id="how" ref={darkRef} aria-labelledby="how-title">
          <div className="wrap">
            <SectionHead id="how-title" title="How it works" label="/ describe · launch · prove · keep checking">
              Building the page is the easy part. The point is the proof: a real test order that reaches you, plain-English
              fixes when something breaks, and quiet checks after launch.
            </SectionHead>
            <Steps />
          </div>
        </section>
      </div>

      <section className="dark dark-cont on-dark" id="proof" aria-labelledby="proof-title">
        <div className="wrap">
          <SectionHead id="proof-title" title="How the proof works" label="/ one real test order, hop by hop">
            Before we call your shop ready, a real test order travels the same path a customer's would. Each hop is saved
            with its time and the server that answered, and your report only claims what was saved.
          </SectionHead>
          <ol className="hops">
            {HOPS.map((h, i) => (
              <Reveal as="li" key={h.name} delay={i * 0.05} className="hop">
                <span className="label">/0{i + 1}</span>
                <strong>{h.name}</strong>
                <span>{h.text}</span>
              </Reveal>
            ))}
          </ol>
        </div>
      </section>

      <section className="dark dark-cont on-dark" id="watch" aria-labelledby="watch-title">
        <div className="wrap">
          <SectionHead id="watch-title" title="We keep watching after launch" label="/ not a one-off check">
            Launch day isn't the end. For every live shop, we keep checking on a schedule, fix what we safely can, and tell
            you about the rest.
          </SectionHead>
          <ol className="watch-grid">
            {WATCH.map((w, i) => (
              <Reveal as="li" key={w.title} delay={i * 0.06} className={`watch-item${i === 3 ? " watch-fix" : ""}`}>
                <span className="label">{w.when}</span>
                <strong id={i === 3 ? "fix" : undefined}>{w.title}</strong>
                <p>{w.text}</p>
              </Reveal>
            ))}
          </ol>
          <details className="tech-details">
            <summary>Technical details</summary>
            <ul>
              <li>Every 15 minutes: the shop's A record points at our server, and HTTPS answers with a valid certificate.</li>
              <li>
                Daily: the same, plus MX, SPF, DKIM and DMARC records, a comparison of the DNS records against the backup
                taken at launch, and a test order with a fresh code through the public form (proof: form POST accepted,
                SMTP accepted; IMAP or the owner's tap for delivery).
              </li>
              <li>
                Failures are re-checked after 60 seconds. The Doctor (Claude) only chooses from a fixed playbook in code:
                re-point the A record, re-add MX, re-add SPF/DKIM/DMARC, retry the certificate, or restore the DNS backup.
                Code applies it and re-checks.
              </li>
              <li>Alerts go to the owner's sign-in email, once per problem until it passes again.</li>
              <li>Renewal warnings: certificate at 7 and 1 days left; domain and team mailbox at 30, 7 and 1 days.</li>
            </ul>
          </details>
          <div style={{ height: "clamp(3rem, 7vw, 6rem)" }} />
        </div>
      </section>

      <section className="dark dark-cont on-dark" aria-labelledby="pieces-title">
        <div className="wrap">
          <SectionHead id="pieces-title" title="Built on GoDaddy" label="/ the pieces we set up for you">
            We do the technical parts on GoDaddy for you, and check each one before we call it done.
          </SectionHead>
          <Marquee />
          <div style={{ height: "clamp(3rem, 7vw, 6rem)" }} />
          <SectionHead id="promises-title" title="Our promises" label="/ safety first" />
          <ul className="promise-grid">
            {PROMISES.map(([title, text], i) => (
              <Reveal as="li" className="promise" key={title} delay={i * 0.08}>
                <div className="title">{title}</div>
                <p>{text}</p>
              </Reveal>
            ))}
          </ul>
        </div>
      </section>

      <section className="check-any" id="check" aria-labelledby="check-title">
        <div className="wrap">
          <Reveal>
            <p className="eyebrow">Read-only check</p>
            <h2 id="check-title">Check any address</h2>
            <p className="tagline">
              Already have a website? Type its address and we'll look, from the outside, at whether it opens securely and
              whether its email is set up so orders don't land in spam. We only read public information: we change
              nothing, send no email and keep nothing about the address.
            </p>
            <CheckAnyAddress />
          </Reveal>
        </div>
      </section>

      <section className="security-sec" id="security" aria-labelledby="security-title">
        <div className="wrap">
          <Reveal>
            <p className="eyebrow">Security &amp; privacy</p>
            <h2 id="security-title">Your shop is yours alone.</h2>
            <ul className="security-list">
              <li>No passwords: you sign in with a link we email you.</li>
              <li>Only you can open your shop's details, orders and reports. Anyone else just gets “not found”.</li>
              <li>Nothing is bought and no setting changes without your approval, and settings are backed up first.</li>
              <li>We never ask for Aadhaar, PAN, bank or card numbers, or your home address.</li>
            </ul>
            <p className="small">
              Read our <a href="#/privacy">Privacy page</a> and <a href="#/terms">Terms</a>.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="closing" id="contact" aria-labelledby="who-title">
        <div className="wrap closing-grid">
          <Reveal>
            <p className="eyebrow">Who it's for</p>
            <h2 id="who-title">Home-based, made-to-order sellers.</h2>
            <p className="tagline">
              You take orders on Instagram and WhatsApp, and you'd like a proper shop page customers can order from,
              without learning how websites work.
            </p>
            <ul className="who-groups">
              {WHO.map((g) => (
                <li key={g.id} id={g.id}>
                  <strong>{g.title}</strong>
                  <span>{g.text}</span>
                  {g.demos.length > 0 && (
                    <span className="small">
                      Demo:{" "}
                      {g.demos.map(([href, label], i) => (
                        <span key={href}>
                          {i > 0 && " · "}
                          <a href={href}>{label}</a>
                        </span>
                      ))}
                    </span>
                  )}
                </li>
              ))}
            </ul>
            <div className="actions">
              <a className="btn btn-primary" href="#/new">
                Try it yourself
              </a>
              <a className="btn btn-ghost" href="/demo/meera">
                See a demo shop
              </a>
            </div>

          </Reveal>
          <Reveal delay={0.1}>
            <p className="eyebrow">Contact us</p>
            <ContactForm />
          </Reveal>
        </div>
      </section>
    </div>
  );
}

/** One headline line that rises out of a mask on first load. */
function Line({ i, children }: { i: number; children: ReactNode }) {
  const calm = useCalm();
  return (
    <span className="line" style={{ overflow: "hidden", paddingBottom: "0.06em" }}>
      <motion.span
        style={{ display: "inline-block" }}
        initial={calm ? false : { y: "105%" }}
        animate={{ y: 0 }}
        transition={{ duration: 0.9, delay: 0.1 + i * 0.09, ease: EASE }}
      >
        {children}
      </motion.span>
    </span>
  );
}

/** Fades content up when it scrolls into view, and back out when it leaves (so scrolling up reverses it). */
function Reveal({
  children,
  delay = 0,
  className,
  as = "div",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
  as?: "div" | "li";
}) {
  const calm = useCalm();
  const Tag = as === "li" ? motion.li : motion.div;
  return (
    <Tag
      className={className}
      initial={calm ? false : { opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: false, amount: 0.25 }}
      transition={{ duration: 0.7, delay, ease: EASE }}
    >
      {children}
    </Tag>
  );
}

function SectionHead({ id, title, label, children }: { id: string; title: string; label: string; children?: ReactNode }) {
  const calm = useCalm();
  return (
    <div className="section-head">
      <div className="meta">
        <Reveal>
          <h2 id={id}>{title}</h2>
        </Reveal>
        <span className="label">{label}</span>
      </div>
      <motion.div
        className="rule"
        initial={calm ? false : { scaleX: 0 }}
        whileInView={{ scaleX: 1 }}
        viewport={{ once: false, amount: 1 }}
        transition={{ duration: 1.1, ease: EASE }}
      />
      {children && (
        <Reveal delay={0.1}>
          <p>{children}</p>
        </Reveal>
      )}
    </div>
  );
}

function Steps() {
  const [active, setActive] = useState(0);
  const [hoverable, setHoverable] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(hover: hover) and (pointer: fine)");
    setHoverable(mq.matches);
  }, []);
  return (
    <ol className="steps">
      {STEPS.map((s, i) => (
        <Reveal as="li" key={s.title} delay={i * 0.07} className={`step-li${active === i ? " active" : ""}`}>
          <button
            type="button"
            className={`step${active === i ? " active" : ""}`}
            aria-expanded={active === i}
            onClick={() => setActive(i)}
            onFocus={() => setActive(i)}
            onMouseEnter={hoverable ? () => setActive(i) : undefined}
          >
            <span className="label">/0{i + 1}</span>
            {s.icon}
            <span className="step-title">{s.title}</span>
            <span className="step-desc">
              <span>
                <span className="txt">{s.text}</span>
              </span>
            </span>
          </button>
        </Reveal>
      ))}
    </ol>
  );
}

function Marquee() {
  const calm = useCalm();
  const group = (hidden: boolean, list = [...PIECES, ...PIECES]) => (
    <div className="marquee-group" aria-hidden={hidden || undefined}>
      {list.map(([name, text], i) => (
        <div className="tile" key={i}>
          <span className="label">/ GoDaddy</span>
          <div>
            <strong>{name}</strong>
            <span>{text}</span>
          </div>
        </div>
      ))}
    </div>
  );
  if (calm) return <div className="marquee-static">{group(false, PIECES)}</div>;
  return (
    <div className="marquee">
      <div className="marquee-track">
        {group(false)}
        {group(true)}
      </div>
    </div>
  );
}

/** Abstract "launch layers": six soft, rounded layers (site, name, email, order, proof…) that breathe gently and
 * fan apart as you scroll. Each layer is a static SVG on its own GPU layer; only transforms animate, so it stays smooth. */
const LAYERS = [
  { fill: "url(#lw-g-ink)", side: "#141412" },
  { fill: "url(#lw-g-plum)", side: "#7a4a63" },
  { fill: "url(#lw-g-amber)", side: "#cf7a33" },
  { fill: "url(#lw-g-coral)", side: "#d9776a" },
  { fill: "url(#lw-g-lime)", side: "#a6bb34" },
  { fill: "url(#lw-g-paper)", side: "#d6cab4" },
];
const BASE_Y = 340; // centre of the lowest layer
const STEP = 42; // gap between layers at rest

function HeroShape({ progress }: { progress: MotionValue<number> }) {
  const calm = useCalm();
  // One scroll value drives everything; each layer reads it through a cheap linear map.
  const spread = useTransform(progress, [0, 1], [0, calm ? 0 : 1]);
  const ys = LAYERS.map((_, i) => useTransform(spread, (v) => -v * i * 22)); // eslint-disable-line react-hooks/rules-of-hooks
  const ringY = useTransform(spread, (v) => -v * 150);
  const tilt = useTransform(spread, (v) => -v * 6);
  return (
    <motion.div
      className="hero-shape"
      aria-hidden
      initial={calm ? false : { opacity: 0, y: 30, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 1.2, delay: 0.2, ease: EASE }}
    >
      <motion.div className="shape-rot" style={{ rotate: tilt }}>
        <svg className="shape-layer" viewBox="0 0 400 460">
          <Defs />
          <ellipse cx="200" cy="420" rx="168" ry="30" fill="url(#lw-g-shadow)" />
        </svg>
        {LAYERS.map((l, i) => (
          <motion.div key={i} className="shape-layer" style={{ y: ys[i] }}>
            <div className={calm ? "shape-layer" : "shape-layer breathe"} style={{ animationDelay: `${-i * 0.45}s` }}>
              <svg viewBox="0 0 400 460">
                <Pebble cy={BASE_Y - i * STEP} fill={l.fill} side={l.side} size={1 - i * 0.035} />
                {i === LAYERS.length - 1 && <Seal cy={BASE_Y - i * STEP} />}
              </svg>
            </div>
          </motion.div>
        ))}
        <motion.div className="shape-layer" style={{ y: ringY }}>
          <div className={calm ? "shape-layer" : "shape-layer orbit"}>
            <svg viewBox="0 0 400 460">
              <ellipse cx="200" cy="40" rx="122" ry="26" fill="none" stroke="url(#lw-g-ring)" strokeWidth="3" />
              <circle cx="312" cy="30" r="20" fill="url(#lw-g-ball)" />
              <circle cx="90" cy="50" r="9" fill="url(#lw-g-ball2)" />
            </svg>
          </div>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}

/** An isometric rounded square ("pebble") with a smooth extruded edge. */
function Pebble({ cy, fill, side, size }: { cy: number; fill: string; side: string; size: number }) {
  const half = 104 * size, r = 46 * size, depth = 16;
  const iso = (y: number) => `translate(200 ${y}) scale(1 0.56) rotate(45)`;
  const rect = (paint: string, y: number, key?: number) => (
    <rect key={key} x={-half} y={-half} width={half * 2} height={half * 2} rx={r} fill={paint} transform={iso(y)} />
  );
  return (
    <g>
      {/* the edge: a few copies stepping down, so the side reads as one smooth curved band */}
      {Array.from({ length: 6 }, (_, k) => rect(side, cy + depth - k * (depth / 6), k))}
      {rect(fill, cy)}
      <rect
        x={-half + 6}
        y={-half + 6}
        width={half * 2 - 12}
        height={half * 2 - 12}
        rx={r - 4}
        fill="none"
        stroke="rgba(255,255,255,0.35)"
        strokeWidth="2"
        transform={iso(cy)}
      />
    </g>
  );
}

function Seal({ cy }: { cy: number }) {
  return (
    <g>
      <ellipse cx="200" cy={cy} rx="42" ry="24" fill="#161614" />
      <path d={`M183 ${cy + 1} q6 4 11 7 q10 -8 22 -15`} fill="none" stroke="#dcf06a" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
}

function Defs() {
  const lin = (id: string, a: string, b: string) => (
    <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stopColor={a} />
      <stop offset="1" stopColor={b} />
    </linearGradient>
  );
  return (
    <defs>
      {lin("lw-g-ink", "#4a4a45", "#191917")}
      {lin("lw-g-plum", "#f0c9dc", "#b7799a")}
      {lin("lw-g-amber", "#ffd9ad", "#f09a50")}
      {lin("lw-g-coral", "#ffd0c4", "#ee8f80")}
      {lin("lw-g-lime", "#f6fcc4", "#cde353")}
      {lin("lw-g-paper", "#ffffff", "#efe6d6")}
      <linearGradient id="lw-g-ring" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stopColor="rgba(31,31,29,0)" />
        <stop offset="0.5" stopColor="rgba(31,31,29,0.45)" />
        <stop offset="1" stopColor="rgba(31,31,29,0)" />
      </linearGradient>
      <radialGradient id="lw-g-ball" cx="0.35" cy="0.3" r="0.75">
        <stop offset="0" stopColor="#fbffd9" />
        <stop offset="0.45" stopColor="#dcf06a" />
        <stop offset="1" stopColor="#7f8f1f" />
      </radialGradient>
      <radialGradient id="lw-g-ball2" cx="0.35" cy="0.3" r="0.75">
        <stop offset="0" stopColor="#ffe7d1" />
        <stop offset="1" stopColor="#e0803d" />
      </radialGradient>
      <radialGradient id="lw-g-shadow" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stopColor="rgba(60,40,10,0.26)" />
        <stop offset="1" stopColor="rgba(60,40,10,0)" />
      </radialGradient>
    </defs>
  );
}

function ContactForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.contact(name, email, message, website);
      setSent(r.message);
      setMessage("");
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(String(err), 0));
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div className="status status-ok" role="status">
        <p>{sent}</p>
      </div>
    );
  }
  return (
    <form className="card" onSubmit={submit}>
      <label className="field">
        <span>Your name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} autoComplete="name" />
      </label>
      <label className="field">
        <span>Your email</span>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} autoComplete="email" />
        <small>So we can reply. We don't add you to any list.</small>
      </label>
      <label className="field">
        <span>Message</span>
        <textarea rows={4} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={3000} />
      </label>
      <label className="hp" aria-hidden>
        Leave this empty
        <input tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
      </label>
      {error && <ErrorBox error={error} />}
      <button className="btn btn-primary" type="submit" disabled={busy || !name.trim() || !email.trim() || !message.trim()}>
        {busy ? "Sending…" : "Send message"}
      </button>
    </form>
  );
}

function CheckAnyAddress() {
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<{ address: string; results: AddressResult[] } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await api.checkAddress(address.trim()));
    } catch (err) {
      setResult(null);
      setError(err instanceof ApiError ? err : new ApiError(String(err), 0));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card check-card">
      <form className="check-form" onSubmit={submit}>
        <label className="field">
          <span>Web address</span>
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="myshop.com"
            inputMode="url"
            autoCapitalize="off"
            autoCorrect="off"
            maxLength={300}
          />
        </label>
        <button className="btn btn-primary" type="submit" disabled={busy || !address.trim()}>
          {busy ? "Checking…" : "Check it"}
        </button>
      </form>
      {error && <ErrorBox error={error} />}
      {result && (
        <>
          <p className="muted">
            Read-only results for <strong>{result.address}</strong>:
          </p>
          <ul className="rows checks">
            {result.results.map((r, i) => (
              <li key={`${r.check}-${i}`} className={r.ok === false ? "bad" : r.ok ? "ok" : "st-pending"}>
                <span className="icon" aria-hidden>
                  {r.ok === false ? "✕" : r.ok ? "✓" : "–"}
                </span>
                <div className="body">
                  <div className="title">{r.plain}</div>
                  {r.detail && <div className="muted mono">{r.detail}</div>}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

