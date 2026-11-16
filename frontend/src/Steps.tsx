import { useEffect, useState } from "react";
import { api, Business } from "./api";

/** The 5-step flow: Describe → Review → Name → Approve → Launch & report. */
export type StepId = "describe" | "review" | "name" | "approve" | "report";

const LABELS: Record<StepId, string> = {
  describe: "Describe",
  review: "Review",
  name: "Name",
  approve: "Approve",
  report: "Launch & report",
};
const ORDER: StepId[] = ["describe", "review", "name", "approve", "report"];

type StepLink = { id: StepId; label: string; href: string | null; done: boolean };

/** Which steps are done, and where each one lives, from the shop's own state. */
export function stepsFor(biz: Business | null): StepLink[] {
  const plan = biz?.latest_plan ?? null;
  const ran = !!plan && plan.status !== "draft";
  const live = biz?.status === "live";
  return ORDER.map((id) => {
    if (!biz) return { id, label: LABELS[id], href: null, done: false };
    switch (id) {
      case "describe":
        return { id, label: LABELS[id], href: null, done: true };
      case "review":
        return { id, label: LABELS[id], href: `#/b/${biz.id}`, done: !!plan || live };
      case "name":
        return { id, label: LABELS[id], href: `#/b/${biz.id}/launch`, done: !!plan || live };
      case "approve":
        return { id, label: LABELS[id], href: plan ? `#/b/${biz.id}/plan/${plan.id}` : null, done: ran || live };
      case "report":
        return { id, label: LABELS[id], href: ran || live ? `#/b/${biz.id}/report` : null, done: live };
    }
  });
}

/** Where to pick up a half-finished shop from My shops. */
export function resumeHash(biz: Business): string {
  const plan = biz.latest_plan;
  if (biz.status === "live" || plan?.status === "done") return `#/b/${biz.id}/report`;
  if (plan) return `#/b/${biz.id}/plan/${plan.id}`;
  return `#/b/${biz.id}`;
}

export function resumeLabel(biz: Business): string {
  const plan = biz.latest_plan;
  if (biz.status === "live" || plan?.status === "done") return "Report";
  if (plan?.status === "draft") return "Continue: approve";
  if (plan?.status === "running" || plan?.status === "approved") return "See the launch";
  if (plan) return "Continue the launch";
  return "Continue";
}

/** The step header: where you are, and links back to steps already done. Loads the shop itself. */
export function StepHeader({ current, businessId }: { current: StepId; businessId?: number }) {
  const [biz, setBiz] = useState<Business | null>(null);
  useEffect(() => {
    if (businessId === undefined) return;
    api.get(businessId).then(setBiz).catch(() => setBiz(null));
  }, [businessId, current]);
  const steps = stepsFor(biz);
  const here = ORDER.indexOf(current);
  return (
    <nav className="stepper" aria-label="Steps">
      <ol>
        {steps.map((s, i) => {
          const isHere = s.id === current;
          const state = isHere ? "here" : s.done || i < here ? "done" : "todo";
          const linkable = !isHere && s.href !== null && (s.done || i < here);
          return (
            <li key={s.id} className={`stepper-${state}`} aria-current={isHere ? "step" : undefined}>
              {linkable ? (
                <a href={s.href!}>
                  <span className="n">{i + 1}</span> {s.label}
                </a>
              ) : (
                <span>
                  <span className="n">{state === "done" ? "✓" : i + 1}</span> {s.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
      <p className="sr-only">
        Step {here + 1} of 5: {LABELS[current]}
      </p>
    </nav>
  );
}
