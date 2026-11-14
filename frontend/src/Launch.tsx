import { useEffect, useState } from "react";
import { api, ApiError, Business, NameIdea, Plan, Step, usd } from "./api";
import { goTo } from "./App";
import { ErrorBox } from "./Describe";

/** Step 3: choose where the site goes — free address now, or the seller's own name. */
export function LaunchChoice({ businessId }: { businessId: number }) {
  const [biz, setBiz] = useState<Business | null>(null);
  const [names, setNames] = useState<NameIdea[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

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

  const makePlan = (mode: "sandbox" | "full", domain?: string) =>
    run(mode, async () => {
      const p = await api.createPlan(businessId, mode, domain);
      goTo(`#/plan/${p.id}`);
    });

  if (!biz) return error ? <ErrorBox error={error} /> : <p>Loading…</p>;
  const freeHost = biz.site_url ? new URL(biz.site_url).host : "";

  return (
    <>
      <h1>Put {biz.profile.name} online</h1>
      <p className="tagline">Pick where your website lives. You'll see every step and the total cost before anything happens.</p>

      <section className="card choice">
        <h2>Free address</h2>
        <p>
          <strong>{freeHost}</strong> — ready in a few minutes, costs nothing. You can move to your own name later.
        </p>
        <button className="btn btn-primary" disabled={!!busy} onClick={() => makePlan("sandbox")}>
          {busy === "sandbox" ? "Preparing…" : "Use the free address"}
        </button>
      </section>

      <section className="card choice">
        <h2>Your own name</h2>
        <p>Like meerascakes.in. We suggest names that are really available, with their price.</p>
        {names === null ? (
          <button
            className="btn btn-ghost"
            disabled={!!busy}
            onClick={() => run("names", async () => setNames(await api.names(businessId)))}
          >
            {busy === "names" ? "Finding names…" : "Suggest names"}
          </button>
        ) : names.length === 0 ? (
          <p className="muted">We couldn't find a free name right now. Try again later, or use the free address.</p>
        ) : (
          <ul className="names">
            {names.map((n) => (
              <li key={n.domain}>
                <span>
                  <strong>{n.domain}</strong> <span className="muted">{usd(n.price_usd)} for the first year</span>
                </span>
                <button className="btn btn-ghost btn-sm" disabled={!!busy} onClick={() => makePlan("full", n.domain)}>
                  {busy === "full" ? "Preparing…" : "Choose"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {error && <ErrorBox error={error} />}
      <p>
        <a href={`#/b/${businessId}`}>← Back to your details</a>
      </p>
    </>
  );
}

const STATUS_ICON: Record<Step["status"], string> = {
  pending: "○",
  running: "◌",
  done: "✅",
  skipped: "➖",
  failed: "⚠️",
  blocked: "⛔",
};

/** Step 4–5: the approval card (draft) and then the live step log (polled). */
export function PlanView({ planId }: { planId: number }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [name, setName] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = () => api.plan(planId).then(setPlan).catch(setError);
  useEffect(() => {
    load();
  }, [planId]);

  const active = plan && (plan.status === "approved" || plan.status === "running");
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(load, 1000);
    return () => window.clearInterval(t);
  }, [active]);

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
        <h1>Check and approve</h1>
        <p className="tagline">Nothing is bought or changed until you tap Approve.</p>
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
                          {c.type} {c.name === "@" ? c.zone : `${c.name}.${c.zone}`}
                        </td>
                      </tr>
                      <tr>
                        <th>Before</th>
                        <td>{c.before_text.length ? c.before_text.join("\n") : "(none)"}</td>
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
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Meera Iyer" maxLength={80} />
          </label>
          <label className="agree">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} /> I agree to these
            changes{plan.total_cost_usd > 0 ? ` and the cost of ${usd(plan.total_cost_usd)}` : ""}.
          </label>
          {error && <ErrorBox error={error} />}
          <div className="actions">
            <button
              className="btn btn-primary"
              disabled={busy || !agreed || !name.trim()}
              onClick={() => act(() => api.approve(plan.id, name.trim()))}
            >
              {busy ? "Starting…" : "Approve and launch"}
            </button>
            <a className="btn btn-ghost" href={`#/b/${plan.business_id}/launch`}>
              Go back
            </a>
          </div>
        </section>
      </>
    );
  }

  const stopped = plan.status === "failed" || plan.status === "blocked";
  return (
    <>
      <h1>
        {plan.status === "done" ? "Your website is on!" : stopped ? "Launch paused" : "Launching your website…"}
      </h1>
      <p className="tagline">{plan.site_host}</p>
      <ol className="card steplog" aria-live="polite">
        {plan.steps.map((s) => (
          <li key={s.id} className={`st-${s.status}`}>
            <span className="icon" aria-hidden>
              {STATUS_ICON[s.status]}
            </span>
            <div>
              <div className="title">{s.title}</div>
              {s.message && <div className="msg">{s.message}</div>}
              <details>
                <summary>Details</summary>
                <p>{s.detail}</p>
                {s.started_at && <p className="muted">Started {new Date(s.started_at).toLocaleTimeString()}</p>}
              </details>
            </div>
          </li>
        ))}
      </ol>
      {error && <ErrorBox error={error} />}
      <div className="actions">
        {stopped && (
          <button className="btn btn-primary" disabled={busy} onClick={() => act(() => api.resume(plan.id))}>
            {busy ? "Resuming…" : "Resume"}
          </button>
        )}
        {plan.status === "done" && plan.site_url && (
          <a className="btn btn-primary" href={plan.site_url} target="_blank" rel="noreferrer">
            Open my website
          </a>
        )}
        <a className="btn btn-ghost" href={`#/b/${plan.business_id}`}>
          Back to your details
        </a>
      </div>
    </>
  );
}
