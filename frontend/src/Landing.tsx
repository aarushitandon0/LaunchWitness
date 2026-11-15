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
    title: "Check your website",
    text: "We turn it into your website. Fix anything we got wrong, then pick a free address or your own name with its real price.",
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
    title: "Approve every change",
    text: "You see every step, every setting we'll change (before and after) and the exact cost. Nothing happens until you say yes.",
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
    title: "Get proof it works",
    text: "We launch it, then prove it: the site opens securely, your email is set up, and a real test order lands in your inbox. Anything broken is repaired or undone.",
    icon: (
      <svg viewBox="0 0 64 64" className="step-icon" aria-hidden>
        <path d="M32 7l20 7v15c0 13-8.5 23-20 28C20.5 52 12 42 12 29V14z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M23.5 31.5l6 6 11-12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

const PIECES = [
  ["Domains", "Your own name, found, priced and adopted"],
  ["DNS", "Every setting backed up before it changes"],
  ["Email", "orders@ your name, signed and protected"],
  ["VPS", "Your shop served from a GoDaddy server"],
  ["HTTPS", "A secure padlock, checked for real"],
  ["Monitoring", "Quiet checks every 15 minutes after launch"],
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
                Website builders stop at “your site is ready”. LaunchWitness proves it can take a customer’s order —
                a real test order has to land in your inbox — fixes it when it can’t, and keeps watching after launch.
                No website yet? Type a few lines and your price list and we build one too.
              </p>
              <div className="hero-meta">
                <a className="btn btn-primary" href="#/try">
                  Try it (practice mode)
                </a>
                <a className="dotlink" href="/build">
                  How this was built
                </a>
              </div>
              <p className="small">Practice mode uses a pretend GoDaddy: nothing is bought and no real settings change.</p>
            </motion.div>
          </div>
          <motion.div className="hero-dim" style={{ opacity: dim }} aria-hidden />
          <div className="scroll-cue" aria-hidden>
            Scroll <span />
          </div>
        </motion.section>

        <section className="dark on-dark" id="how" ref={darkRef} aria-labelledby="how-title">
          <div className="wrap">
            <SectionHead id="how-title" title="How it works" label="/ 4 steps · about 10 minutes">
              The point is the proof: a real test order reaching your inbox, plain-English fixes when something breaks,
              and a check-in every 15 minutes after launch. Building the site is the easy part.
            </SectionHead>
            <Steps />
          </div>
        </section>
      </div>

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

      <section className="closing" id="contact" aria-labelledby="meera-title">
        <div className="wrap closing-grid">
          <Reveal>
            <p className="eyebrow">Who it's for</p>
            <h2 id="meera-title">Meera bakes eggless cakes in Pune.</h2>
            <p className="tagline">
              Her customers find her on Instagram and order in messages, but she has no website, no business email, and
              no time to learn what “DNS” means. LaunchWitness turns her two lines and a price list into a live shop with
              her own name and email, and checks that a real order reaches her inbox before her first customer does.
            </p>
            <div className="actions">
              <a className="btn btn-primary" href="#/try">
                Try it yourself
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

/** Abstract "launch layers": four slabs (site, name, email, proof) that drift apart as you scroll. Pure SVG. */
function HeroShape({ progress }: { progress: MotionValue<number> }) {
  const calm = useCalm();
  const spread = (k: number) => useTransform(progress, [0, 1], [0, calm ? 0 : -k]);
  const ys = [spread(0), spread(26), spread(56), spread(92)];
  const ballY = useTransform(progress, [0, 1], [0, calm ? 0 : -140]);
  const rot = useTransform(progress, [0, 1], [0, calm ? 0 : -8]);
  const slabs = [
    { cy: 330, top: "url(#lw-g-ink)", left: "#0d0d0c", right: "#2a2a27" },
    { cy: 272, top: "url(#lw-g-amber)", left: "#c9772c", right: "#e3934a" },
    { cy: 214, top: "url(#lw-g-lime)", left: "#a9bd3a", right: "#c3d851" },
    { cy: 156, top: "url(#lw-g-paper)", left: "#d8cdb8", right: "#ece3d2" },
  ];
  return (
    <motion.div
      className="hero-shape"
      aria-hidden
      initial={calm ? false : { opacity: 0, y: 30, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 1.2, delay: 0.2, ease: EASE }}
    >
      {/* Each layer is its own HTML element so the browser can move it on the GPU without repainting the drawing. */}
      <motion.div className="shape-rot" style={{ rotate: rot }}>
        <svg className="shape-layer" viewBox="0 0 400 460">
          <Defs />
          <ellipse cx="200" cy="420" rx="170" ry="34" fill="url(#lw-g-shadow)" />
        </svg>
        {slabs.map((s, i) => (
          <motion.div key={i} className="shape-layer" style={{ y: ys[i] }}>
            <svg viewBox="0 0 400 460">
              <Slab cy={s.cy} top={s.top} left={s.left} right={s.right} />
              {i === 3 && (
                <g>
                  <ellipse cx="200" cy={s.cy} rx="44" ry="25" fill="#161614" />
                  <path
                    d={`M182 ${s.cy + 1} l12 6 l22 -14`}
                    fill="none"
                    stroke="#dcf06a"
                    strokeWidth="5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </g>
              )}
            </svg>
          </motion.div>
        ))}
        <motion.div className="shape-layer" style={{ y: ballY }}>
          <div className="shape-layer float">
            <svg viewBox="0 0 400 460">
              <circle cx="292" cy="70" r="24" fill="url(#lw-g-ball)" />
            </svg>
          </div>
        </motion.div>
      </motion.div>
    </motion.div>
  );
}

function Defs() {
  return (
    <defs>
      <linearGradient id="lw-g-ink" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#3b3b37" />
        <stop offset="1" stopColor="#151513" />
      </linearGradient>
      <linearGradient id="lw-g-amber" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#ffd2a1" />
        <stop offset="1" stopColor="#f29a52" />
      </linearGradient>
      <linearGradient id="lw-g-lime" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#f3fbb8" />
        <stop offset="1" stopColor="#cfe556" />
      </linearGradient>
      <linearGradient id="lw-g-paper" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#ffffff" />
        <stop offset="1" stopColor="#efe6d6" />
      </linearGradient>
      <radialGradient id="lw-g-ball" cx="0.35" cy="0.3" r="0.75">
        <stop offset="0" stopColor="#fbffd9" />
        <stop offset="0.45" stopColor="#dcf06a" />
        <stop offset="1" stopColor="#7f8f1f" />
      </radialGradient>
      <radialGradient id="lw-g-shadow" cx="0.5" cy="0.5" r="0.5">
        <stop offset="0" stopColor="rgba(60,40,10,0.28)" />
        <stop offset="1" stopColor="rgba(60,40,10,0)" />
      </radialGradient>
    </defs>
  );
}

function Slab({ cy, top, left, right }: { cy: number; top: string; left: string; right: string }) {
  const cx = 200, w = 150, h = 86, t = 20;
  return (
    <g strokeLinejoin="round">
      <path d={`M${cx - w} ${cy} L${cx} ${cy + h} L${cx} ${cy + h + t} L${cx - w} ${cy + t} Z`} fill={left} stroke={left} strokeWidth="6" />
      <path d={`M${cx} ${cy + h} L${cx + w} ${cy} L${cx + w} ${cy + t} L${cx} ${cy + h + t} Z`} fill={right} stroke={right} strokeWidth="6" />
      <path d={`M${cx} ${cy - h} L${cx + w} ${cy} L${cx} ${cy + h} L${cx - w} ${cy} Z`} fill={top} stroke={top} strokeWidth="6" />
    </g>
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
            {result.results.map((r) => (
              <li key={r.check} className={r.ok === false ? "bad" : r.ok ? "ok" : "st-pending"}>
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

