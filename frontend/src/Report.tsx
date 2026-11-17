import { StepHeader } from "./Steps";
import { AnimatePresence, motion } from "framer-motion";
import { ShopLink } from "./ShopLink";
import { useEffect, useState } from "react";
import { api, ApiError, CheckRow, Hop, Renewal, Report } from "./api";
import { Cross, Dot, EASE, Spinner, Tick, TypeIn, useCalm } from "./motion";
import { ErrorBox } from "./Describe";
import { DoctorTimeline, KIND_WORDS, KindTag, LOOKS, SureTag } from "./Findings";
import type { DemoFaultName, Incident } from "./api";

const time = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "";

const clock = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });

function ago(iso: string | null): string {
  if (!iso) return "";
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.round(min / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

/** "Form accepted 14:02:11 → Mail server accepted 14:02:12 → In the inbox 14:02:19", from stored evidence only. */
function HopTrace({ hops }: { hops: Hop[] }) {
  if (!hops.length) return null;
  return (
    <ol className="hops" aria-label="What we saw, step by step">
      {hops.map((h, i) => (
        <li key={i} title={[h.server, h.message_id, h.answer].filter(Boolean).join(" · ")}>
          <span className="hop-title">{h.title}</span> <span className="hop-at">{clock(h.at)}</span>
        </li>
      ))}
    </ol>
  );
}

// ---------- the assistant note, shown once on the next page ----------

const NOTE = (id: number) => `lw-note-${id}`;

export function rememberNote(id: number, note: string) {
  try {
    window.sessionStorage.setItem(NOTE(id), note);
  } catch {
    /* ignore */
  }
}

export function takeNote(id: number): string | null {
  try {
    const n = window.sessionStorage.getItem(NOTE(id));
    window.sessionStorage.removeItem(NOTE(id));
    return n;
  } catch {
    return null;
  }
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
  const unknown = state === "final" && (c.kind === "couldnt_check" || c.kind === "couldnt_finish");
  const red = state === "failed" || state === "doctor" || state === "typed" || (state === "final" && !c.passed && !unknown);
  const amber = state === "final" && c.passed && c.state === "needs_you"; // accepted, not yet proven delivered
  const green = ((state === "final" && c.passed) || state === "fixed") && !amber;
  const showDoctor = !!doctor && (state === "doctor" || state === "typed" || state === "fixed" || (state === "final" && !c.first_passed));
  return (
    <motion.li
      className={unknown ? "st-unknown" : red ? "bad row-bad" : amber ? "needs-you" : green ? "ok" : "st-pending"}
      layout="position"
      transition={{ duration: 0.4, ease: EASE }}
    >
      <span className="icon">
        {state === "waiting" ? (
          <Dot />
        ) : state === "checking" ? (
          <Spinner />
        ) : unknown ? (
          <span className="q-mark" aria-label="Not known">?</span>
        ) : red ? (
          <Cross />
        ) : amber ? (
          <Cross tone="wait" />
        ) : (
          <Tick animate={live} />
        )}
      </span>
      <div className="body">
        <div className="title">
          {c.title}
          {green && c.fixed && (
            <motion.span className="badge" initial={live ? { opacity: 0, scale: 0.8 } : false} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.3, ease: EASE }}>
              Fixed by us
            </motion.span>
          )}
          {state === "final" && <KindTag kind={c.kind} />}
          {state === "final" && <SureTag sure={c.sure} />}
        </div>
        {(red || amber || unknown) && <div className="msg">{c.plain}</div>}
        {state === "final" && c.kind && c.kind !== "passed" && c.kind !== "failed" && (
          <div className="kind-line">{KIND_WORDS[c.kind].line}</div>
        )}
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
            <HopTrace hops={c.hops ?? []} />
            <div className="muted when">Checked {time(c.at)}</div>
            {c.doctor && <DoctorTimeline d={c.doctor} passed={c.passed} fixed={c.fixed} />}
            <details className="tech-details">
              <summary>Technical details</summary>
              <p className="mono">{c.detail}</p>
              {c.doctor && c.doctor.trace.length > 0 && (
                <>
                  <p>What we looked at before deciding (these looks only read; they changed nothing):</p>
                  <ol className="doctor-trace">
                    {c.doctor.trace.map((t, i) => (
                      <li key={i}>
                        {LOOKS[t.tool] ?? t.tool}: <span className="mono">{t.short_result}</span>
                      </li>
                    ))}
                  </ol>
                </>
              )}
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
  const headText = playing || run?.status === "running" ? "Checking that everything works…" : rep.headline;

  return (
    <>
      <StepHeader current="report" businessId={businessId} />
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
      {rep.practice && !waiting && (
        <p className="practice" role="note">
          Practice run. These results come from a pretend GoDaddy and a pretend inbox, not the real internet.
        </p>
      )}
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
        {launched && !waiting && (
          <ShopLink businessId={businessId} siteUrl={rep.business.site_url} isPublic={rep.business.public} />
        )}
        {!launched && (
          <a className="btn btn-primary" href={`#/b/${businessId}/launch`}>
            Launch my website →
          </a>
        )}
      </div>
      {error && <ErrorBox error={error} />}

      {launched && !waiting && (
        <SymptomBox businessId={businessId} left={rep.symptoms_left} onStarted={load} />
      )}

      {run && run.status === "done" && (
        <>
          <h2>What we checked</h2>
          <p className="muted">
            {run.trigger === "launch" ? "Right after your launch" : "When you pressed “Run checks now”"},{" "}
            {time(run.started_at)}.
          </p>
          {!playing && (
            <p className={`proof-count${rep.proof.stale ? " stale" : ""}`} role="status">
              <strong>
                {rep.proof.proven} of {rep.proof.total} proven
                {rep.proof.needs_you > 0 && `, ${rep.proof.needs_you} needs you`}
              </strong>
              {rep.proof.last_checked_at && <> · last checked {ago(rep.proof.last_checked_at)}</>}
              {rep.proof.stale && <> · these results are more than a day old: run the checks again</>}
            </p>
          )}
          <ul className={`card rows checks${rep.proof.stale && !playing ? " stale" : ""}`}>
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

      {rep.launch && !waiting && (
        <details className="launch-steps">
          <summary>
            Launch steps: {rep.launch.steps.filter((s) => s.status === "done").length} of {rep.launch.steps.length} finished
          </summary>
          <ol className="tech">
            {rep.launch.steps.map((s, i) => (
              <li key={i}>
                {s.title}: {s.status === "done" ? "finished" : s.status}
                {s.message && s.status !== "done" ? ` (${s.message})` : ""}
              </li>
            ))}
          </ol>
        </details>
      )}

      {rep.confirmed_by_you && (
        <>
          <h2>Checked by you</h2>
          <p className="muted small">
            These are your own checks. They are kept apart from what our machines proved above.
          </p>
          <ul className="card confirmed-list">
            {rep.confirmed_by_you.map((c) => (
              <li key={c.what} className={c.at ? "ok" : "todo"}>
                <span className="mark" aria-hidden>
                  {c.at ? "✓" : "○"}
                </span>
                <span>
                  {c.label}
                  <br />
                  <small className="muted">
                    {c.at
                      ? `Confirmed by you · ${new Date(c.at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })}`
                      : "Not confirmed yet"}
                  </small>
                </span>
              </li>
            ))}
          </ul>
        </>
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
                    : r.attempts.length === 0
                      ? "We didn't change anything: there is no safe automatic fix for this, so it needs you (the steps are above, under this check)."
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

      {!waiting && rep.incidents.length > 0 && <IncidentTimeline items={rep.incidents} />}

      {launched && (
        <>
          <h2>Keeping an eye on it</h2>
          <section className="card monitor">
            <p>
              {mon.enabled
                ? `We check that your website opens every ${mon.every_minutes} minutes, and your email settings and a test order once a day.`
                : "Regular checks are switched off on this server. Use “Run checks now” any time."}
            </p>
            <p className="muted">
              The daily test order proves your order form works and our mail server accepted the email. It proves the
              email reached you only when you tap “Yes, I got it” in it.
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
              {mon.public_resolvers && (
                <div>
                  <dt>Seen from the wider internet</dt>
                  <dd title={mon.public_resolvers.answer}>
                    {mon.public_resolvers.agree ? "✅" : "ℹ️"} {mon.public_resolvers.title}
                    {mon.public_resolvers.practice ? " (practice)" : ""} · {time(mon.public_resolvers.at)}
                  </dd>
                </div>
              )}
            </dl>
            {rep.renewals && <RenewalsCard items={rep.renewals} practice={rep.practice} />}
            {!rep.business.has_owner_email && (
              <p className="warn">
                <a href="#/signin">Sign in</a> so we can warn you if something breaks (we write to your sign-in address).
              </p>
            )}
          </section>
        </>
      )}

      {launched && run && run.status === "done" && <SharePanel businessId={businessId} practice={rep.practice} />}

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

const STAGED: { fault: DemoFaultName; label: string; what: string; practiceOnly: boolean }[] = [
  { fault: "a_record", label: "Address leads nowhere", what: "the shop's address record is really removed (guarded write); the Doctor looks it up and re-points it", practiceOnly: false },
  { fault: "marker", label: "Parked page, not the shop", what: "the address opens a parked page without the shop marker (pretend); the Doctor opens it and re-points the address", practiceOnly: true },
  { fault: "cert", label: "Padlock not working", what: "the certificate fails until asked for again (pretend); the Doctor opens the page and asks for a new one", practiceOnly: true },
  { fault: "smtp_login", label: "Mail sign-in refused", what: "our mail service refuses the sign-in for one run (pretend); the Doctor tries it and hands it to us with exact steps", practiceOnly: true },
];

function DemoSwitch({ businessId, rep, onChange }: { businessId: number; rep: Report; onChange: () => void }) {
  const [error, setError] = useState<ApiError | null>(null);
  const set = (fault: DemoFaultName) =>
    api
      .setDemoFault(businessId, fault)
      .then(() => {
        setError(null);
        onChange();
      })
      .catch(setError);
  const armed = (rep.demo_fault ?? "") as DemoFaultName;
  const staged = STAGED.find((f) => f.fault === armed);
  const full = rep.plan?.mode === "full";
  return (
    <section className="card admin demo-switch">
      <h2>Demo switch (team only)</h2>
      <p>
        {staged
          ? `Armed: ${staged.label.toLowerCase()}: ${staged.what}. Press “Run checks now”. It is used up by that one run.`
          : armed
            ? `Armed: the ${armed === "dmarc" ? "fake-email protection (DMARC)" : "mail delivery setting (MX)"} will be removed before the next check. Press “Run checks now”.`
            : "Off. Stage one fault before the next check, so the Doctor's investigation shows in the demo."}
      </p>
      <div className="fault-grid" role="group" aria-label="Staged faults">
        {STAGED.map((f) => (
          <button
            key={f.fault}
            type="button"
            className={`btn btn-ghost btn-sm${armed === f.fault ? " is-armed" : ""}`}
            aria-pressed={armed === f.fault}
            disabled={f.practiceOnly && !rep.practice}
            title={f.practiceOnly && !rep.practice ? "Practice shops only: we never break a real shop's page, padlock or mail." : f.what}
            onClick={() => set(f.fault)}
          >
            {f.label}
            {f.practiceOnly && <small className="muted"> · practice</small>}
          </button>
        ))}
      </div>
      {full && (
        <div className="actions">
          <button className="btn btn-ghost btn-sm" disabled={armed === "dmarc"} onClick={() => set("dmarc")}>
            Remove DMARC before next check
          </button>
          <button className="btn btn-ghost btn-sm" disabled={armed === "mx"} onClick={() => set("mx")}>
            Remove MX instead
          </button>
        </div>
      )}
      {armed && (
        <div className="actions">
          <button className="btn btn-ghost btn-sm" onClick={() => set("")}>
            Turn off
          </button>
        </div>
      )}
      {error && <ErrorBox error={error} />}
    </section>
  );
}

// ---------- "Describe the problem" (S12): her words go to the Doctor as data ----------

const SYMPTOM_CHIPS = [
  "My shop doesn't open",
  "Customers see a security warning",
  "My address opens someone else's page",
  "Order emails aren't reaching me",
];

function SymptomBox({ businessId, left, onStarted }: { businessId: number; left: number; onStarted: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [sent, setSent] = useState(false);
  return (
    <section className="card symptom" aria-labelledby="symptom-title">
      <h2 id="symptom-title">Describe the problem</h2>
      <p className="muted small">
        Tell us in your own words what you or a customer saw. We run every check again, and for anything that fails our
        assistant reads your words while it looks. It can only look and choose from our fixed list of safe fixes;
        nothing you type can make it do anything else.
      </p>
      <div className="chips" role="group" aria-label="Examples">
        {SYMPTOM_CHIPS.map((c) => (
          <button key={c} type="button" className="chip" onClick={() => setText(c)} aria-pressed={text === c}>
            {c}
          </button>
        ))}
      </div>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await api.describeProblem(businessId, text.trim());
            setSent(true);
            setText("");
            onStarted();
          } catch (err) {
            setError(err instanceof ApiError ? err : new ApiError(String(err), 0));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="field">
          <span className="sr-only">What went wrong</span>
          <textarea
            rows={2}
            maxLength={500}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setSent(false);
            }}
            placeholder="For example: my sister says the page shows a warning on her phone"
          />
        </label>
        <div className="actions">
          <button className="btn btn-primary btn-sm" type="submit" disabled={busy || left <= 0 || text.trim().length < 3}>
            {busy ? "Starting…" : "Check with this in mind"}
          </button>
          <span className="muted small">{left > 0 ? `${left} left today` : "None left today: try again tomorrow."}</span>
        </div>
      </form>
      {sent && (
        <p className="status status-ok" role="status">
          Checking now. The answer appears under “What we checked” below.
        </p>
      )}
      {error && <ErrorBox error={error} />}
    </section>
  );
}

// ---------- incident timeline (S12): from stored results only ----------

const INCIDENT_WORDS: Record<Incident["status"], string> = {
  open: "Open",
  fixed: "Fixed",
  needs_you: "Needs you",
  keeps_breaking: "Keeps breaking",
};

export function IncidentTimeline({ items }: { items: Incident[] }) {
  return (
    <>
      <h2>What went wrong, and what happened next</h2>
      <p className="muted small">Every problem from the last 30 days, from our stored results. Nothing here is guessed.</p>
      <ol className="card incidents">
        {items.map((e, i) => (
          <li key={`${e.check}-${e.opened_at}-${i}`} className={`incident inc-${e.status}`}>
            <div className="incident-head">
              <strong>{e.title}</strong>
              <span className={`inc-tag inc-tag-${e.status}`}>{INCIDENT_WORDS[e.status]}</span>
              <span className="muted small">{time(e.opened_at)}</span>
            </div>
            <ol className="incident-steps">
              {e.steps.map((s, j) => (
                <li key={j}>{s.what}</li>
              ))}
            </ol>
            {e.next && (
              <p className="incident-next">
                <strong>Next step for you:</strong> {e.next}
              </p>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}

// ---------- share the proof (read-only link, no customer details) ----------

function SharePanel({ businessId, practice }: { businessId: number; practice: boolean }) {
  const [active, setActive] = useState<boolean | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    api.shareStatus(businessId).then((s) => setActive(s.active)).catch(() => setActive(false));
  }, [businessId]);
  const run = (fn: () => Promise<void>) => fn().catch((e) => setError(e instanceof ApiError ? e : new ApiError(String(e), 0)));
  return (
    <>
      <h2>Share this proof</h2>
      <section className="card">
        <p className="muted">
          A read-only page with these results and times, for a customer or a friend. It shows no customer details
          {practice ? ", and it says these are practice results" : ""}. You can turn the link off at any time.
        </p>
        {url && (
          <p className="mono share-url">
            <a href={url} target="_blank" rel="noopener">
              {url}
            </a>
          </p>
        )}
        <div className="actions">
          <button
            className="btn btn-ghost btn-sm"
            onClick={() =>
              run(async () => {
                setUrl((await api.share(businessId)).url);
                setActive(true);
              })
            }
          >
            {active ? "Make a new link (the old one stops)" : "Make a share link"}
          </button>
          {active && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={() =>
                run(async () => {
                  await api.unshare(businessId);
                  setActive(false);
                  setUrl(null);
                })
              }
            >
              Turn the link off
            </button>
          )}
        </div>
        {error && <ErrorBox error={error} />}
      </section>
    </>
  );
}

// ---------- "Yes, I got it" (the test order email links here; the button, not the link, records it) ----------

export function GotItPage() {
  const token = new URLSearchParams(window.location.hash.split("?")[1] ?? "").get("token") ?? "";
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  if (done !== null)
    return (
      <>
        <h1>Thank you</h1>
        <p className="tagline">
          We've recorded that the test order reached you{done ? ` for ${done}` : ""}. Your report now shows it as proven.
        </p>
      </>
    );
  return (
    <>
      <p className="eyebrow">Test order</p>
      <h1>Did our test order email reach you?</h1>
      <p className="tagline">Tap the button to tell us. It proves your customers' orders reach your inbox.</p>
      {error && <ErrorBox error={error} />}
      <button
        className="btn btn-primary"
        disabled={busy || !token}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            setDone((await api.confirmTestOrder(token)).shop);
          } catch (e) {
            setError(e instanceof ApiError ? e : new ApiError(String(e), 0));
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Saving…" : "Yes, I got it"}
      </button>
    </>
  );
}

const RENEWAL_STATE: Record<Renewal["state"], string> = {
  ok: "Fine",
  soon: "Soon",
  urgent: "Very soon",
  lapsed: "Ran out",
  unknown: "Not known yet",
};

/** Renewals (S10): what runs out, when, and who renews it. LaunchWitness never renews or pays by itself. */
export function RenewalsCard({ items, practice }: { items: Renewal[]; practice: boolean }) {
  return (
    <div className="renewals">
      <h3>Renewals</h3>
      {practice && <p className="practice">Practice: these dates come from the pretend GoDaddy.</p>}
      <ul>
        {items.map((r) => (
          <li key={r.what} className={`renewal renewal-${r.state}`}>
            <strong>{r.label}</strong>
            <span>
              {r.days_left === null ? RENEWAL_STATE.unknown : r.days_left < 0 ? RENEWAL_STATE.lapsed : `${r.days_left} days left`}
              {r.state !== "ok" && r.state !== "unknown" && ` · ${RENEWAL_STATE[r.state]}`}
            </span>
            <span className="muted">{r.plain}</span>
          </li>
        ))}
      </ul>
      <p className="muted">We never renew or pay for anything automatically. Money always needs a person.</p>
    </div>
  );
}
