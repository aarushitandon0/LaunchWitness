import { motion } from "framer-motion";
import { ShopLink } from "./ShopLink";
import { useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  Business,
  lastAssistantNote,
  NameIdea,
  Plan,
  Step,
  usd,
} from "./api";
import { Cross, Dot, EASE, Spinner, Tick, useCalm } from "./motion";
import { goTo } from "./App";
import { ErrorBox } from "./Describe";
import { useMe } from "./Account";

/** Step 3: choose where the site goes — free address now, or the seller's own name. */
export function LaunchChoice({ businessId }: { businessId: number }) {
  const [biz, setBiz] = useState<Business | null>(null);
  const [names, setNames] = useState<NameIdea[] | null>(null);
  const [namesNote, setNamesNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const me = useMe(true);

  useEffect(() => {
    api.get(businessId).then(setBiz).catch(setError);
  }, [businessId]);

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e), 0));
    } finally {
      setBusy(null);
    }
  };

  const makePlan = (mode: "sandbox" | "full", domain?: string, real = false) =>
    run(real ? "real" : mode, async () => {
      const p = await api.createPlan(businessId, mode, domain, real);
      goTo(`#/b/${businessId}/plan/${p.id}`);
    });

  if (!biz) return error ? <ErrorBox error={error} /> : <p>Loading…</p>;
  const freeHost = biz.site_url ? new URL(biz.site_url).host : "";
  // Shown only for convenience: the server checks the account again when the plan is made and approved.
  const canLaunchForReal = !!me?.user && me.user.status === "approved" && !biz.guest;

  return (
    <>
      <p className="eyebrow">Step 3 of 5 · choose an address</p>
      <h1>Put {biz.profile.name} online</h1>
      <p className="tagline">
        Pick where your website lives. You'll see every step and the total cost
        before anything happens.
      </p>

      {canLaunchForReal && (
        <section className="card choice">
          <h2>Launch for real</h2>
          <p>
            <strong>{freeHost}</strong> goes on the internet for your customers. It costs nothing. You'll see every
            change before anything happens.
          </p>
          <button className="btn btn-primary" disabled={!!busy} onClick={() => makePlan("sandbox", undefined, true)}>
            {busy === "real" ? "Preparing…" : "Launch for real"}
          </button>
        </section>
      )}

      {biz.practice && (
        <section className="card choice">
          <h2>Practice launch</h2>
          <p>
            Try every step on <strong>{freeHost}</strong> against a pretend GoDaddy. Nothing goes on the internet and
            nothing is bought.
          </p>
          <button
            className={canLaunchForReal ? "btn btn-ghost" : "btn btn-primary"}
            disabled={!!busy}
            onClick={() => makePlan("sandbox")}
          >
            {busy === "sandbox" ? "Preparing…" : "Practise with the free address"}
          </button>
        </section>
      )}

      {biz.practice && (
      <section className="card choice">
        <h2>Your own name (practice only)</h2>
        <p>
          Like meerascakes.in. Real launches use the free address for now; you can practise this one. We suggest names
          that are really available, with their price.
        </p>
        {names === null ? (
          <button
            className="btn btn-ghost"
            disabled={!!busy}
            onClick={() =>
              run("names", async () => {
                setNames(await api.names(businessId));
                setNamesNote(lastAssistantNote);
              })
            }
          >
            {busy === "names" ? "Finding names…" : "Suggest names"}
          </button>
        ) : names.length === 0 ? (
          <p className="muted">
            We couldn't find a free name right now. Try again later, or use the
            free address.
          </p>
        ) : (
          <>
            {namesNote && (
              <p className="muted assistant-note" role="status">
                {namesNote}
              </p>
            )}
            <ul className="names">
              {names.map((n) => (
                <li key={n.domain}>
                  <span>
                    <strong>{n.domain}</strong>{" "}
                    <span className="muted">
                      {usd(n.price_usd)} for the first year
                    </span>
                  </span>
                  <button
                    className="btn btn-ghost btn-sm"
                    disabled={!!busy}
                    onClick={() => makePlan("full", n.domain)}
                  >
                    {busy === "full" ? "Preparing…" : "Choose"}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      )}

      {error && <ErrorBox error={error} />}
      <p>
        <a href={`#/b/${businessId}`}>← Back to your details</a>
      </p>
    </>
  );
}

function StepMark({ status }: { status: Step["status"] }) {
  if (status === "done") return <Tick />;
  if (status === "running") return <Spinner />;
  if (status === "blocked") return <Cross tone="wait" />;
  if (status === "failed") return <Cross />;
  return <Dot />;
}

/** Gap between log lines appearing, so the launch reads as a story even when the work is instant. */
const LINE_GAP_MS = 420;

/** Step 4–5: the approval card (draft) and then the live step log (polled). */
export function PlanView({
  businessId,
  planId,
}: {
  businessId: number;
  planId: number;
}) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [name, setName] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = () => api.plan(businessId, planId).then(setPlan).catch(setError);
  useEffect(() => {
    load();
  }, [planId]);

  const calm = useCalm();
  const active =
    plan && (plan.status === "approved" || plan.status === "running");
  // Stream the log only for a launch we see happen (opened as a draft or while running).
  // Opening a finished launch later shows the whole log at once.
  const streaming = useRef<boolean | null>(null);
  if (plan && streaming.current === null)
    streaming.current =
      !calm &&
      plan.status !== "done" &&
      plan.status !== "failed" &&
      plan.status !== "blocked";
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(load, 1000);
    return () => window.clearInterval(t);
  }, [active]);

  const steps = plan?.steps ?? [];
  const reached = steps.filter((s) => s.status !== "pending").length;
  const target = !streaming.current
    ? steps.length
    : active
      ? Math.min(steps.length, reached + 1)
      : plan?.status === "draft"
        ? 0
        : steps.length;
  const visible = streaming.current ? Math.min(shown, target) : steps.length;
  useEffect(() => {
    if (!streaming.current || shown >= target) return;
    const t = window.setTimeout(
      () => setShown((n) => n + 1),
      shown === 0 ? 150 : LINE_GAP_MS,
    );
    return () => window.clearTimeout(t);
  }, [shown, target]);

  // When a launch we were watching finishes (and its log has played), go straight to the proof.
  useEffect(() => {
    if (
      streaming.current &&
      plan?.status === "done" &&
      visible >= steps.length
    ) {
      const t = window.setTimeout(() => goTo(`#/b/${businessId}/report`), 1500);
      return () => window.clearTimeout(t);
    }
  }, [plan?.status, visible, steps.length]);

  if (!plan) return error ? <ErrorBox error={error} /> : <p>Loading…</p>;

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

  const costLine =
    plan.total_cost_usd > 0
      ? `${usd(plan.total_cost_usd)} for ${plan.zone} (first year)`
      : plan.mode === "sandbox"
        ? "Free"
        : `Nothing to buy — you already own ${plan.zone}`;

  if (plan.status === "draft") {
    return (
      <>
        <p className="eyebrow">Step 4 of 5 · approve</p>
        <h1>Check and approve</h1>
        <p className="tagline">
          Nothing is bought or changed until you tap Approve.
        </p>
        <section className="card approval">
          <dl className="summary">
            <div>
              <dt>Your website</dt>
              <dd>{plan.site_host}</dd>
            </div>
            <div>
              <dt>Total cost</dt>
              <dd className="cost">{costLine}</dd>
            </div>
            {plan.email_plan_estimate_usd !== null && (
              <div>
                <dt>Email plan, bought separately on GoDaddy</dt>
                <dd>
                  about {usd(plan.email_plan_estimate_usd)} a year{" "}
                  <span className="muted">
                    (estimate — not part of the total; you pay GoDaddy for it
                    yourself)
                  </span>
                </dd>
              </div>
            )}
            <div>
              <dt>Orders are emailed to</dt>
              <dd>{plan.mailbox}</dd>
            </div>
          </dl>

          <h2>What we'll do</h2>
          <ol className="todo">
            {plan.steps.map((s) => (
              <li key={s.id}>{s.title}</li>
            ))}
          </ol>

          <h2>Settings we'll change</h2>
          <ul className="settings">
            {plan.changes.map((c) => (
              <li key={`${c.type}-${c.name}`}>
                {c.say}
                <details>
                  <summary>Details</summary>
                  <table className="diff">
                    <tbody>
                      <tr>
                        <th>Record</th>
                        <td>
                          {c.type}{" "}
                          {c.name === "@" ? c.zone : `${c.name}.${c.zone}`}
                        </td>
                      </tr>
                      <tr>
                        <th>Before</th>
                        <td>
                          {c.before_text.length
                            ? c.before_text.join("\n")
                            : "(none)"}
                        </td>
                      </tr>
                      <tr>
                        <th>After</th>
                        <td className="after">{c.after_text.join("\n")}</td>
                      </tr>
                    </tbody>
                  </table>
                </details>
              </li>
            ))}
          </ul>
          <details>
            <summary>Technical details of each step</summary>
            <ul className="tech">
              {plan.steps.map((s) => (
                <li key={s.id}>
                  <strong>{s.title}:</strong> {s.detail}
                </li>
              ))}
            </ul>
          </details>

          <label className="field">
            <span>Your name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Meera Iyer"
              maxLength={80}
            />
          </label>
          <label className="agree">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
            />{" "}
            I agree to these changes
            {plan.total_cost_usd > 0
              ? ` and the cost of ${usd(plan.total_cost_usd)}`
              : ""}
            .
          </label>
          {error && <ErrorBox error={error} />}
          <div className="actions">
            <button
              className="btn btn-primary"
              disabled={busy || !agreed || !name.trim()}
              onClick={() =>
                act(() => api.approve(businessId, plan.id, name.trim()))
              }
            >
              {busy ? "Starting…" : "Approve and launch"}
            </button>
            <a
              className="btn btn-ghost"
              href={`#/b/${plan.business_id}/launch`}
            >
              Go back
            </a>
          </div>
        </section>
      </>
    );
  }

  const stopped = plan.status === "failed" || plan.status === "blocked";
  const waitingToBuy =
    plan.practice &&
    plan.status === "blocked" &&
    plan.steps.some((s) => s.kind === "get_domain" && s.status === "blocked");
  const shownSteps = plan.steps.slice(0, visible);
  const doneCount = shownSteps.filter(
    (s) => s.status === "done" || s.status === "skipped",
  ).length;
  const finished = plan.status === "done" && visible >= plan.steps.length;
  return (
    <>
      <p className="eyebrow">{plan.site_host}</p>
      <h1>
        {finished ? (
          "Your website is on!"
        ) : stopped && visible >= plan.steps.length ? (
          "Launch paused"
        ) : (
          <>
            <span className="live-dot" aria-hidden />
            Launching your website…
          </>
        )}
      </h1>
      <div className="progress" aria-hidden>
        <motion.span
          initial={false}
          animate={{
            scaleX: plan.steps.length ? doneCount / plan.steps.length : 0,
          }}
          transition={{ duration: 0.6, ease: EASE }}
        />
      </div>
      <ol className="card rows steplog" aria-live="polite">
        {shownSteps.map((s) => (
          <motion.li
            key={s.id}
            className={`st-${s.status}`}
            initial={streaming.current ? { opacity: 0, y: 10 } : false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: EASE }}
          >
            <span className="icon">
              <StepMark status={s.status} />
            </span>
            <div className="body">
              <div className="title">{s.title}</div>
              {s.message && <div className="msg">{s.message}</div>}
              <details>
                <summary>Details</summary>
                <p>{s.detail}</p>
                {s.started_at && (
                  <p className="muted">
                    Started {new Date(s.started_at).toLocaleTimeString()}
                  </p>
                )}
              </details>
            </div>
          </motion.li>
        ))}
      </ol>
      {waitingToBuy && (
        <p className="practice" role="note">
          Practice mode: nothing is really bought. Tap “Pretend I bought it” to
          carry on as if you had bought {plan.zone} on godaddy.com.
        </p>
      )}
      {error && <ErrorBox error={error} />}
      <div className="actions">
        {waitingToBuy && (
          <button
            className="btn btn-primary"
            disabled={busy}
            onClick={() => act(() => api.practiceBuy(businessId, plan.id))}
          >
            {busy ? "Continuing…" : "Pretend I bought it (practice)"}
          </button>
        )}
        {stopped && !waitingToBuy && (
          <button
            className="btn btn-primary"
            disabled={busy}
            onClick={() => act(() => api.resume(businessId, plan.id))}
          >
            {busy ? "Resuming…" : "Resume"}
          </button>
        )}
        {finished && (
          <a className="btn btn-primary" href={`#/b/${businessId}/report`}>
            See your launch report →
          </a>
        )}
        {finished && <ShopLink businessId={businessId} siteUrl={plan.site_url} isPublic={plan.public} />}
        <a className="btn btn-ghost" href={`#/b/${plan.business_id}`}>
          Back to your details
        </a>
      </div>
    </>
  );
}
