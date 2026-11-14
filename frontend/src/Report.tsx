import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api, ApiError, CheckRow, keys, Report } from "./api";
import { Cross, Dot, EASE, Spinner, Tick, TypeIn, useCalm } from "./motion";
import { goTo } from "./App";
import { ErrorBox } from "./Describe";

const time = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "";

// ---------- owner link, shown once right after "Make my website" ----------

const NEW_LINK = (id: number) => `lw-new-link-${id}`;

export function rememberNewLink(id: number, link: string) {
  try {
    window.sessionStorage.setItem(NEW_LINK(id), link);
  } catch {
    /* ignore */
  }
}

function takeNewLink(id: number): string | null {
  try {
    return window.sessionStorage.getItem(NEW_LINK(id));
  } catch {
    return null;
  }
}

export function OwnerLinkPage({ businessId }: { businessId: number }) {
  const [link] = useState(() => takeNewLink(businessId));
  const [copied, setCopied] = useState(false);

  const done = () => {
    try {
      window.sessionStorage.removeItem(NEW_LINK(businessId)); // shown once
    } catch {
      /* ignore */
    }
    goTo(`#/b/${businessId}`);
  };

  if (!link) {
    return (
      <>
        <h1>Your private link</h1>
        <p>For your safety we only show your private link once, right after you describe your business.</p>
        <a className="btn btn-primary" href={`#/b/${businessId}`}>
          Continue
        </a>
      </>
    );
  }
  return (
    <>
      <p className="eyebrow">Before you go on</p>
      <h1>Save your private link</h1>
      <p className="tagline">
        This link is the key to your shop. Anyone who has it can change your website, so keep it to yourself. We can't
        send it again, so save it now: copy it into a note, or send it to yourself on WhatsApp or email.
      </p>
      <section className="card">
        <label className="field">
          <span>Your private link</span>
          <input readOnly value={link} onFocus={(e) => e.target.select()} aria-label="Your private link" />
        </label>
        <div className="actions">
          <button
            className="btn btn-primary"
            onClick={() =>
              navigator.clipboard
                ?.writeText(link)
                .then(() => setCopied(true))
                .catch(() => setCopied(false))
            }
          >
            {copied ? "Copied" : "Copy link"}
          </button>
          <button className="btn btn-ghost" onClick={done}>
            I've saved it, continue →
          </button>
        </div>
        <p className="muted">On this phone or computer you're already signed in, so you won't need the link here.</p>
      </section>
    </>
  );
}

// ---------- launch report ----------

type Phase = "checking" | "failed" | "doctor" | "typed" | "fixed" | "final";
type Seq = { runId: number | null; index: number; phase: Phase; done: boolean };
const PLAYED = (runId: number) => `lw-played-run-${runId}`;
function hasPlayed(runId: number) {
  try {
    return window.localStorage.getItem(PLAYED(runId)) === "1";
  } catch {
    return false;
  }
}
function markPlayed(runId: number) {
  try {
    window.localStorage.setItem(PLAYED(runId), "1");
  } catch {
    /* ignore */
  }
}

/** One check row. `state` is where the playback is for this row; "final" shows the real result. */
function CheckLine({
  c,
  doctor,
  state,
  onTyped,
}: {
  c: CheckRow;
  doctor: string;
  state: Phase | "waiting";
  onTyped: () => void;
}) {
  const live = state !== "final";
  const red = state === "failed" || state === "doctor" || state === "typed" || (state === "final" && !c.passed);
  const green = (state === "final" && c.passed) || state === "fixed";
  const showDoctor = !!doctor && (state === "doctor" || state === "typed" || state === "fixed" || (state === "final" && !c.first_passed));
  return (
    <motion.li
      className={red ? "bad row-bad" : green ? "ok" : "st-pending"}
      layout="position"
      transition={{ duration: 0.4, ease: EASE }}
    >
      <span className="icon">
        {state === "waiting" ? <Dot /> : state === "checking" ? <Spinner /> : red ? <Cross /> : <Tick animate={live} />}
      </span>
      <div className="body">
        <div className="title">
          {c.title}
          {green && c.fixed && (
            <motion.span className="badge" initial={live ? { opacity: 0, scale: 0.8 } : false} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.3, ease: EASE }}>
              Fixed by us
            </motion.span>
          )}
        </div>
        {red && <div className="msg">{c.plain}</div>}
        {showDoctor && (
          <motion.div
            className="doctor"
            initial={live ? { opacity: 0, y: 6 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: EASE }}
          >
            <div className="doctor-label">What went wrong</div>
            {state === "doctor" ? <TypeIn text={doctor} onDone={onTyped} /> : doctor}
          </motion.div>
        )}
        {state === "fixed" && <div className="fixnote">We fixed it and checked again: it works now.</div>}
        {state === "final" && (
          <>
            <div className="muted when">Checked {time(c.at)}</div>
            <details>
              <summary>Details</summary>
              <p className="mono">{c.detail}</p>
            </details>
          </>
        )}
      </div>
    </motion.li>
  );
}

export function ReportPage({ businessId }: { businessId: number }) {
  const [rep, setRep] = useState<Report | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api
      .report(businessId)
      .then((r) => {
        setRep(r);
        setError(null);
      })
      .catch(setError);
  useEffect(() => {
    load();
  }, [businessId]);

  const checking = rep?.run?.status === "running" || rep?.headline === "Your launch is still running";
  useEffect(() => {
    if (!checking) return;
    const t = window.setInterval(load, 1000);
    return () => window.clearInterval(t);
  }, [checking]);

  // ---- check-by-check playback, once per check run ----
  const calm = useCalm();
  const [seq, setSeq] = useState<Seq>({ runId: null, index: 0, phase: "checking", done: true });
  const runId = rep?.run?.status === "done" ? rep.run.id : null;
  useEffect(() => {
    if (runId === null) return;
    if (calm || hasPlayed(runId)) setSeq({ runId, index: 0, phase: "checking", done: true });
    else setSeq({ runId, index: 0, phase: "checking", done: false });
  }, [runId]);
  useEffect(() => {
    const checks = rep?.run?.checks ?? [];
    if (seq.done || seq.runId === null || seq.runId !== runId) return;
    if (seq.index >= checks.length) {
      markPlayed(seq.runId);
      setSeq({ ...seq, done: true });
      return;
    }
    const c = checks[seq.index];
    const hasDoctor = !!rep?.run?.repairs.find((r) => r.check === c.check)?.attempts[0]?.explanation;
    const next = (patch: Partial<Seq>, ms: number) => {
      const t = window.setTimeout(() => setSeq((s) => ({ ...s, ...patch })), ms);
      return () => window.clearTimeout(t);
    };
    const advance = { index: seq.index + 1, phase: "checking" as Phase };
    switch (seq.phase) {
      case "checking":
        return next(c.first_passed ? { phase: "final" } : { phase: "failed" }, 480);
      case "final":
        return next(advance, 260);
      case "failed":
        return next(hasDoctor ? { phase: "doctor" } : advance, hasDoctor ? 800 : 1100);
      case "doctor":
        return; // TypeIn calls onTyped
      case "typed":
        return next(c.passed ? { phase: "fixed" } : advance, 900);
      case "fixed":
        return next(advance, 1100);
    }
  }, [seq, runId]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e), 0));
    } finally {
      setBusy(false);
    }
  };

  if (!rep) return error ? <ErrorBox error={error} /> : <p>Loading…</p>;
  const run = rep.run;
  const mon = rep.monitoring;
  const launched = rep.plan !== null && rep.headline !== "Your business isn't launched yet";

  // Before the playback effect has picked up a new run, treat it as "about to play" (no flash of results).
  const fresh = !!run && run.status === "done" && seq.runId !== run.id && !calm && !hasPlayed(run.id);
  const playing = fresh || (!!run && run.status === "done" && seq.runId === run.id && !seq.done);
  const cur = run && seq.runId === run.id ? seq : { index: 0, phase: "checking" as Phase };
  const waiting = checking || playing;
  const headClass = waiting ? "headline-wait" : rep.ready ? "headline-ok" : "headline-todo";
  const headText = playing ? "Checking that everything works…" : rep.headline;

  return (
    <>
      <p className="eyebrow report-name">Step 5 of 5 · proof · {rep.business.name}</p>
      <motion.div className={`headline ${headClass}`} layout="position" transition={{ duration: 0.4, ease: EASE }}>
        <span className="icon">{waiting ? <Spinner size={30} /> : rep.ready ? <Tick size={30} /> : <Cross size={30} />}</span>
        <AnimatePresence mode="wait" initial={false}>
          <motion.h1
            key={headText}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.35, ease: EASE }}
          >
            {headText}
          </motion.h1>
        </AnimatePresence>
      </motion.div>
      {rep.left.length > 0 && !waiting && (
        <ul className="left">
          {rep.left.map((l, i) => (
            <li key={i}>{l}</li>
          ))}
        </ul>
      )}

      <div className="actions">
        {launched && (
          <button className="btn btn-primary" disabled={busy || waiting} onClick={() => act(() => api.runChecks(businessId))}>
            {waiting ? "Checking…" : busy ? "Starting…" : "Run checks now"}
          </button>
        )}
        {rep.ready && !waiting && rep.business.site_url && (
          <a className="btn btn-ghost" href={rep.business.site_url} target="_blank" rel="noreferrer">
            Open my website
          </a>
        )}
        {!launched && (
          <a className="btn btn-primary" href={`#/b/${businessId}/launch`}>
            Launch my website →
          </a>
        )}
      </div>
      {error && <ErrorBox error={error} />}

      {run && run.status === "done" && (
        <>
          <h2>What we checked</h2>
          <p className="muted">
            {run.trigger === "launch" ? "Right after your launch" : "When you pressed “Run checks now”"},{" "}
            {time(run.started_at)}.
          </p>
          <ul className="card rows checks">
            {run.checks.map((c, i) => (
              <CheckLine
                key={`${run.id}-${c.check}`}
                c={c}
                doctor={run.repairs.find((r) => r.check === c.check)?.attempts[0]?.explanation ?? ""}
                state={!playing || i < cur.index ? "final" : i > cur.index ? "waiting" : cur.phase}
                onTyped={() =>
                  setSeq((s) => (s.runId === run.id && s.index === i && s.phase === "doctor" ? { ...s, phase: "typed" } : s))
                }
              />
            ))}
          </ul>
        </>
      )}
      {run && run.status === "running" && (
        <ul className="card rows checks">
          <li>
            <span className="icon">
              <Spinner />
            </span>
            <div className="body">
              <div className="title">Running every check…</div>
              <div className="muted when">Results appear here in a moment.</div>
            </div>
          </li>
        </ul>
      )}

      {run && !waiting && run.repairs.length > 0 && (
        <>
          <h2>What went wrong, and what we did</h2>
          <ul className="card repairs">
            {run.repairs.map((r) => (
              <li key={r.check}>
                <div className="title">
                  {r.fixed ? "✅" : "⚠️"} {r.title}
                </div>
                {r.attempts[0] && <p className="quote">“{r.attempts[0].explanation}”</p>}
                <p>
                  {r.fixed
                    ? `We fixed it${r.attempts.length > 1 ? ` after ${r.attempts.length} tries` : ""} and checked again: it works now.`
                    : `We tried ${r.attempts.length} time${r.attempts.length === 1 ? "" : "s"} and stopped, so nothing else changes without you.`}
                </p>
                <details>
                  <summary>Details</summary>
                  <ol className="tech">
                    {r.attempts.map((a, i) => (
                      <li key={i}>
                        Try {i + 1}: {a.fix_id || "no fix"} — {a.message} {a.passed ? "(check passed)" : "(still failing)"}
                      </li>
                    ))}
                  </ol>
                </details>
              </li>
            ))}
          </ul>
        </>
      )}

      {launched && (
        <>
          <h2>Keeping an eye on it</h2>
          <section className="card monitor">
            <p>
              {mon.enabled
                ? `We check that your website opens every ${mon.every_minutes} minutes, and your email settings once a day.`
                : "Regular checks are switched off on this server. Use “Run checks now” any time."}
            </p>
            <dl className="summary">
              {mon.last_quick && (
                <div>
                  <dt>Last quick check</dt>
                  <dd>
                    {mon.last_quick.passed ? "✅" : "⚠️"} {time(mon.last_quick.at)}
                  </dd>
                </div>
              )}
              {mon.last_daily && (
                <div>
                  <dt>Last daily check</dt>
                  <dd>
                    {mon.last_daily.passed ? "✅" : "⚠️"} {time(mon.last_daily.at)}
                  </dd>
                </div>
              )}
              {mon.cert_days_left !== null && (
                <div>
                  <dt>Security certificate (renews by itself)</dt>
                  <dd>{mon.cert_days_left} days left</dd>
                </div>
              )}
              {mon.domain_days_left !== null && (
                <div>
                  <dt>Your website name (you renew it on GoDaddy)</dt>
                  <dd>{mon.domain_days_left} days left — we'll remind you 30, 7 and 1 days before</dd>
                </div>
              )}
            </dl>
            {!rep.business.has_owner_email && (
              <p className="warn">
                Add your personal email on <a href={`#/b/${businessId}`}>your details</a> so we can warn you if something
                breaks.
              </p>
            )}
          </section>
        </>
      )}

      {rep.admin && launched && <DemoSwitch businessId={businessId} rep={rep} onChange={load} />}

      <details className="audit">
        <summary>Details: everything that happened ({rep.audit.length})</summary>
        <table className="diff">
          <tbody>
            {rep.audit.map((e, i) => (
              <tr key={i}>
                <td className="nowrap">{time(e.at)}</td>
                <td>
                  <strong>{e.actor}</strong> {e.action} {e.target} → <em>{e.result}</em>
                  {e.detail && <div className="muted">{e.detail}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      <p>
        <a href={`#/b/${businessId}`}>← Back to your details</a>
      </p>
    </>
  );
}

function DemoSwitch({ businessId, rep, onChange }: { businessId: number; rep: Report; onChange: () => void }) {
  const [error, setError] = useState<ApiError | null>(null);
  const set = (fault: "" | "dmarc" | "mx") =>
    api
      .setDemoFault(businessId, fault)
      .then(() => {
        setError(null);
        onChange();
      })
      .catch(setError);
  const armed = rep.demo_fault;
  return (
    <section className="card admin">
      <h2>Demo switch (team only)</h2>
      {rep.plan?.mode !== "full" ? (
        <p className="muted">The demo fault needs a launch on the shop's own name.</p>
      ) : (
        <>
          <p>
            {armed
              ? `Armed: the ${armed === "dmarc" ? "fake-email protection (DMARC)" : "mail delivery setting (MX)"} will be removed before the next check. Press “Run checks now”.`
              : "Off. Arm it to remove one email setting before the next check, so the fix shows in the demo."}
          </p>
          <div className="actions">
            <button className="btn btn-ghost btn-sm" disabled={armed === "dmarc"} onClick={() => set("dmarc")}>
              Remove DMARC before next check
            </button>
            <button className="btn btn-ghost btn-sm" disabled={armed === "mx"} onClick={() => set("mx")}>
              Remove MX instead
            </button>
            {armed && (
              <button className="btn btn-ghost btn-sm" onClick={() => set("")}>
                Turn off
              </button>
            )}
          </div>
        </>
      )}
      {error && <ErrorBox error={error} />}
    </section>
  );
}

// ---------- admin sign-in (this browser only) ----------

export function AdminPage() {
  const [token, setToken] = useState("");
  const [on, setOn] = useState(!!keys.admin());
  const [error, setError] = useState<ApiError | null>(null);
  const signIn = () =>
    api
      .adminCheck(token.trim())
      .then(() => {
        keys.setAdmin(token.trim());
        setOn(true);
        setError(null);
      })
      .catch(setError);
  return (
    <>
      <h1>Team access</h1>
      {on ? (
        <>
          <p>This browser has team access: the demo switch shows on launch reports.</p>
          <button
            className="btn btn-ghost"
            onClick={() => {
              keys.setAdmin(null);
              setOn(false);
            }}
          >
            Remove team access
          </button>
        </>
      ) : (
        <section className="card">
          <label className="field">
            <span>Team token</span>
            <input type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" />
          </label>
          {error && <ErrorBox error={error} />}
          <button className="btn btn-primary" disabled={!token.trim()} onClick={signIn}>
            Sign in
          </button>
        </section>
      )}
    </>
  );
}
