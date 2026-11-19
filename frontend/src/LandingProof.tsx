/** S12: the two interactive landing sections.
 *  HopTrack ("How the proof works"): six hops on a line; "Send a test order" plays a dot hop by hop; each hop opens
 *  a panel (what we check, what we save, and "If it breaks here" with the real words and fix from the code).
 *  WatchDay ("We keep watching after launch"): an example day as 96 fifteen-minute ticks plus the daily runs;
 *  "Something breaks" plays the real monitor sequence.
 *  Every sentence under "If it breaks here" and in the play-through is pinned to the backend by
 *  backend/tests/test_s12_landing_copy.py. Animations use transform and opacity only; reduced motion gets the end state. */
import { useInView } from "framer-motion";
import { useEffect, useId, useRef, useState } from "react";
import { useCalm } from "./motion";

// ---------- How the proof works ----------

type HopInfo = {
  name: string;
  check: string; // what we check
  saved: string; // what we save as evidence
  at: string; // example time stamp
  breaks: { see: string; fix?: string; doctor: string; needsYou: boolean };
};

/** `see`: the checker's own words (app/agents/checker.py). `doctor`: a playbook fix's words (app/incidents.py
 *  FIX_WORDS) or the code-written next step (app/agents/investigator.py). `fix`: the playbook id. */
export const HOP_INFO: HopInfo[] = [
  {
    name: "Address",
    check: "Your shop's address leads to our GoDaddy server. We ask GoDaddy's own nameservers, every one of them.",
    saved: "The answer, which nameserver gave it, and the time.",
    at: "14:02:11",
    breaks: {
      see: "Your address doesn't lead to your website yet.",
      fix: "repoint_site",
      doctor: "We pointed your address at your shop again",
      needsYou: false,
    },
  },
  {
    name: "Secure page",
    check: "The address opens securely, with a valid padlock.",
    saved: "The answer code and the date the padlock certificate runs out.",
    at: "14:02:12",
    breaks: {
      see: "Your website's security certificate isn't working yet.",
      fix: "retry_certificate",
      doctor: "We asked for a new security certificate (the padlock)",
      needsYou: false,
    },
  },
  {
    name: "Your shop",
    check: "The page that opens is really your shop: we look for its own hidden marker.",
    saved: "That the marker was on the page, with the time.",
    at: "14:02:12",
    breaks: {
      see: "Your address opens a page, but it isn't your shop.",
      fix: "repoint_site",
      doctor: "We pointed your address at your shop again",
      needsYou: false,
    },
  },
  {
    name: "Order form",
    check: "A real test order goes in through your shop's own order form, like a customer's.",
    saved: "The form's answer and the time.",
    at: "14:02:13",
    breaks: {
      see: "Your order form didn't accept a test order.",
      doctor:
        "Your order form didn't take our test order, so customers may not be able to order either. Open your shop and try placing an order yourself. If it fails, write to us from the contact form and we'll look at it with you.",
      needsYou: true,
    },
  },
  {
    name: "Mail server",
    check: "The mail server accepts the order email for you.",
    saved: "Which mail server took it, its message id, and the time.",
    at: "14:02:14",
    breaks: {
      see: "Your order form works, but we couldn't send the order email.",
      doctor:
        "This one is on our side, not yours: our mail service refused our own sign-in, so order emails can't go out right now. Your shop still takes orders: look at your Orders page for new ones.",
      needsYou: true,
    },
  },
  {
    name: "Your inbox",
    check: "It reaches you. Proven when you tap “Yes, I got it” in that email.",
    saved: "Your tap on “Yes, I got it”, or the email seen in the inbox, with the time.",
    at: "when you tap",
    breaks: {
      see: "A test order was sent but hasn't arrived in your inbox.",
      doctor:
        "Our test order email was sent but hasn't reached your inbox yet. Look in your spam folder: if it's there, mark it “not spam”. If it isn't anywhere after an hour, write to us from the contact form.",
      needsYou: true,
    },
  },
];

const STEP_MS = 650;

export function HopTrack() {
  const calm = useCalm();
  const [reached, setReached] = useState(-1); // last hop the dot has reached (-1: not sent)
  const [playing, setPlaying] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const timers = useRef<number[]>([]);
  const panelId = useId();
  const n = HOP_INFO.length;
  // S19: when the section first scrolls into view, a glow travels hop 01 → 06 (looks only: it never marks a hop done)
  const trackRef = useRef<HTMLDivElement>(null);
  const seen = useInView(trackRef, { once: true, amount: 0.6 });

  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  function send() {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
    if (calm) {
      setReached(n - 1);
      return;
    }
    setPlaying(true);
    setReached(-1);
    for (let i = 0; i < n; i++) {
      timers.current.push(window.setTimeout(() => setReached(i), 120 + i * STEP_MS));
    }
    timers.current.push(window.setTimeout(() => setPlaying(false), 120 + n * STEP_MS));
  }

  const p = Math.max(0, reached) / (n - 1);
  return (
    <div className="hoptrack">
      <div className="hoptrack-bar">
        <button type="button" className="btn btn-primary" onClick={send} disabled={playing}>
          {reached < 0 ? "Send a test order" : playing ? "Sending…" : "Send it again"}
        </button>
        <span className="hoptrack-note">
          Example: the times are made up. On your report, every time is a real saved one.
        </span>
      </div>
      <div ref={trackRef} className="hoptrack-track" data-pulse={seen && !calm ? "1" : "0"} style={{ ["--p" as string]: p }} data-sent={reached >= 0 ? "1" : "0"}
        data-arrived={reached === n - 1 && !playing ? "1" : "0"}>
        <div className="hoptrack-line" aria-hidden>
          <span className="hoptrack-fill" />
        </div>
        <div className="hoptrack-runner" aria-hidden>
          <span className="hoptrack-dot" />
        </div>
        <div className="hoptrack-pulse" aria-hidden>
          <span />
        </div>
        <ol className="hoptrack-hops" aria-label="The six hops of a test order">
          {HOP_INFO.map((h, i) => {
            const done = i <= reached;
            return (
              <li key={h.name} style={{ ["--i" as string]: i }} className={`hoptrack-hop${done ? " done" : ""}${open === i ? " open" : ""}`}>
                <button
                  type="button"
                  className="hoptrack-node"
                  aria-expanded={open === i}
                  aria-controls={panelId}
                  onClick={() => setOpen(i)}
                  onFocus={() => setOpen(i)}
                >
                  <span className="hoptrack-circle" aria-hidden>
                    <span className="hoptrack-num">0{i + 1}</span>
                    <svg viewBox="0 0 24 24" className="hoptrack-tick">
                      <path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                  <span className="hoptrack-name">{h.name}</span>
                  <span className="hoptrack-at">
                    {done ? (
                      <>
                        <span className="ex">Example</span> {i === n - 1 ? "proven when you tap" : h.at}
                      </>
                    ) : (
                      <span className="sr-only">not reached yet</span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>
      <div role="status" className="sr-only">
        {reached >= 0 ? `Test order reached hop ${reached + 1} of ${n}: ${HOP_INFO[reached].name}.` : ""}
      </div>
      <div id={panelId} className={`hoppanel${open === null ? " empty" : ""}`} aria-live="polite">
        {open === null ? (
          <p className="hoppanel-hint">Pick a hop to see what we check there, what we save, and what happens if it breaks.</p>
        ) : (
          <HopPanel i={open} key={open} />
        )}
      </div>
    </div>
  );
}

function HopPanel({ i }: { i: number }) {
  const h = HOP_INFO[i];
  return (
    <div className="hoppanel-card">
      <span className="hoppanel-tab">/0{i + 1}</span>
      <h3>{h.name}</h3>
      <div className="hoppanel-cols">
        <div>
          <div className="hoppanel-k">What we check</div>
          <p>{h.check}</p>
        </div>
        <div>
          <div className="hoppanel-k">What we save as evidence</div>
          <p>{h.saved}</p>
        </div>
        <div className="hoppanel-breaks">
          <div className="hoppanel-k">If it breaks here</div>
          <p>
            You'd see: <q>{h.breaks.see}</q>
          </p>
          <p>
            {h.breaks.needsYou ? (
              <>
                <strong>Needs you.</strong> The Doctor gives you the exact steps: <q>{h.breaks.doctor}</q>
              </>
            ) : (
              <>
                <strong>Safe fix:</strong> {h.breaks.doctor}, then we check again.
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------- We keep watching after launch ----------

const TICKS = 96; // one every 15 minutes (monitor/scheduler.py QUICK_MINUTES)
const DAILY_AT = 22; // example: tick index of the daily run (05:30)
const RENEW_AT = 24; // example: the renewals look (06:00)
const BREAK_AT = 56; // example: the quick check that fails (14:00)

const hhmm = (tick: number) => `${String(Math.floor(tick / 4)).padStart(2, "0")}:${String((tick % 4) * 15).padStart(2, "0")}`;

function whatRan(t: number): string {
  if (t === DAILY_AT)
    return "Daily check: everything in the quick check, plus the settings that keep order emails out of spam, nothing we set at launch changed, and a real test order through your form.";
  if (t === RENEW_AT) return "Renewals: how long the padlock, your address and our order mailbox have left.";
  return "Quick check: your address still leads to your shop, and it opens securely.";
}

/** The real sequence after a failed quick check (monitor/scheduler.py: recheck after RECHECK_SECONDS with the
 *  Doctor allowed to fix; an email only for what is still broken after that). */
export const BREAK_STEPS: { at: string; text: string; tone: "bad" | "look" | "fix" | "ok" | "mail" }[] = [
  { at: "14:00", text: "Quick check: your address doesn't lead to your shop.", tone: "bad" },
  { at: "14:01", text: "We check again a minute later, to rule out a blip. Still broken.", tone: "bad" },
  { at: "14:01", text: "Looked up where your address leads → it leads nowhere", tone: "look" },
  { at: "14:01", text: "We pointed your address at your shop again", tone: "fix" },
  { at: "14:01", text: "Checked again: working", tone: "ok" },
  {
    at: "",
    text: "No email this time: it's fixed, and your report shows what happened. Had it still been broken, you'd get one email about it, and no more about that problem.",
    tone: "mail",
  },
];

export function WatchDay() {
  const calm = useCalm();
  const [sel, setSel] = useState(BREAK_AT);
  const [step, setStep] = useState(-1); // how far "Something breaks" has played
  const [playing, setPlaying] = useState(false);
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  function play() {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
    setSel(BREAK_AT);
    if (calm) {
      setStep(BREAK_STEPS.length - 1);
      return;
    }
    setPlaying(true);
    setStep(-1);
    BREAK_STEPS.forEach((_, i) => timers.current.push(window.setTimeout(() => setStep(i), 200 + i * 900)));
    timers.current.push(window.setTimeout(() => setPlaying(false), 200 + BREAK_STEPS.length * 900));
  }

  const broken = step >= 0;
  const fixed = step >= 4;
  const label = `${hhmm(sel)}: ${whatRan(sel)}${sel === BREAK_AT && broken ? (fixed ? " (it failed, and was fixed a minute later)" : " (it failed)") : ""}`;
  return (
    <div className="watchday">
      <div className="watchday-head">
        <span className="watchday-title">An example day</span>
        <span className="watchday-legend">
          <span className="lg lg-q" /> every 15 minutes <span className="lg lg-d" /> once a day <span className="lg lg-r" /> renewals
        </span>
      </div>
      <div
        className="watchday-strip"
        role="slider"
        tabIndex={0}
        aria-label="Checks in an example day"
        aria-valuemin={0}
        aria-valuemax={TICKS - 1}
        aria-valuenow={sel}
        aria-valuetext={label}
        onKeyDown={(e) => {
          const d = e.key === "ArrowRight" || e.key === "ArrowUp" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowDown" ? -1 : 0;
          if (e.key === "Home") setSel(0);
          else if (e.key === "End") setSel(TICKS - 1);
          else if (d) setSel((s) => (s + d + TICKS) % TICKS);
          else return;
          e.preventDefault();
        }}
      >
        {Array.from({ length: TICKS }, (_, t) => (
          <span
            key={t}
            className={[
              "tick",
              t === DAILY_AT ? "tick-d" : t === RENEW_AT ? "tick-r" : "",
              t === sel ? "sel" : "",
              t === BREAK_AT && broken ? (fixed ? "tick-fixed" : "tick-bad") : "",
              t % 4 === 0 ? "hour" : "",
            ].join(" ")}
            onMouseEnter={() => setSel(t)}
            onClick={() => setSel(t)}
            aria-hidden
          />
        ))}
      </div>
      <div className="watchday-hours" aria-hidden>
        {["00:00", "06:00", "12:00", "18:00", "24:00"].map((h) => (
          <span key={h}>{h}</span>
        ))}
      </div>
      <div className="watchday-rows" aria-hidden>
        Top row: 00:00 to 12:00 · bottom row: 12:00 to 24:00
      </div>
      <p className="watchday-what" aria-hidden>
        <strong>{hhmm(sel)}</strong> {whatRan(sel)}
      </p>
      <div className="watchday-bar">
        <button type="button" className="btn btn-primary" onClick={play} disabled={playing}>
          {step < 0 ? "Something breaks" : playing ? "Playing…" : "Play it again"}
        </button>
        <span className="watchday-note">Example: the times are made up; the steps are what the code does.</span>
      </div>
      <ol className="breakseq" aria-live="polite" aria-label="What happens when something breaks">
        {BREAK_STEPS.map((s, i) =>
          i <= step ? (
            <li key={i} className={`bs bs-${s.tone}`}>
              {s.at && <span className="bs-at">{s.at}</span>}
              <span>{s.text}</span>
            </li>
          ) : null,
        )}
      </ol>
    </div>
  );
}
