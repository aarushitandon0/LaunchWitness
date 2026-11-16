/** S12: how every finding is shown, wherever it comes from (our shops, "Check any address", "Watch this address").
 *  A small confidence tag, the steps as a short numbered list, the email service by name, and the technical
 *  values only inside "Technical details". Each state has its own words; only a pass looks like a pass. */
import type { AddressResult, CheckRow, DoctorLook } from "./api";

export type Sure = "seen" | "not_seen" | "couldnt_check";

export const SURE_WORDS: Record<Sure, { label: string; hint: string }> = {
  seen: { label: "Seen", hint: "We read this ourselves." },
  not_seen: { label: "Not seen", hint: "We looked, and it wasn't there." },
  couldnt_check: { label: "Couldn't check", hint: "We couldn't read this, so we don't know either way." },
};

export function SureTag({ sure }: { sure?: string }) {
  if (!sure || !(sure in SURE_WORDS)) return null;
  const w = SURE_WORDS[sure as Sure];
  return (
    <span className={`sure sure-${sure}`} title={w.hint}>
      <span className="sr-only">How sure we are: </span>
      {w.label}
    </span>
  );
}

/** "Do this, then that." → ["Do this.", "Then that."]. Keeps sentences whole; never splits inside a value. */
export function stepsOf(text: string): string[] {
  const t = text.trim();
  if (!t) return [];
  return t
    .split(/(?<=[.!?])\s+(?=[A-Z“"(])/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function Steps({ text, label = "What to do" }: { text: string; label?: string }) {
  const steps = stepsOf(text);
  if (!steps.length) return null;
  return (
    <div className="steps-box">
      <div className="steps-label">{label}</div>
      <ol className="steps-list">
        {steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>
    </div>
  );
}

// ---------- "Check any address" / watched addresses ----------

const MAIL = new Set(["email_mx", "email_spf", "email_dkim", "email_dmarc"]);

function mark(ok: boolean | null, sure?: string) {
  if (sure === "couldnt_check") return { cls: "st-unknown", icon: "?", word: "Couldn't check" };
  if (ok === false) return { cls: "bad", icon: "✕", word: "Problem" };
  if (ok) return { cls: "ok", icon: "✓", word: "Good" };
  return { cls: "st-note", icon: "–", word: "Note" };
}

export function AddressFindings({ results }: { results: AddressResult[] }) {
  const provider = results.find((r) => MAIL.has(r.check) && r.provider_label)?.provider_label;
  const web = results.filter((r) => !MAIL.has(r.check));
  const mail = results.filter((r) => MAIL.has(r.check));
  return (
    <>
      {[
        ["Website", web],
        ["Email", mail],
      ].map(([title, list]) =>
        (list as AddressResult[]).length ? (
          <div key={title as string} className="finding-group">
            <h3 className="finding-group-title">{title as string}</h3>
            {title === "Email" && provider && <p className="provider-line">Your email runs on {provider}.</p>}
            <ul className="rows checks findings">
              {(list as AddressResult[]).map((r, i) => {
                const m = mark(r.ok, r.sure);
                return (
                  <li key={`${r.check}-${i}`} className={m.cls}>
                    <span className="icon" aria-hidden>
                      {m.icon}
                    </span>
                    <div className="body">
                      <div className="title">
                        <span className="sr-only">{m.word}: </span>
                        {r.plain} <SureTag sure={r.sure} />
                      </div>
                      {r.ok !== true && r.steps && <Steps text={r.steps} />}
                      {r.detail && (
                        <details className="tech-details">
                          <summary>Technical details</summary>
                          <p className="mono">{r.detail}</p>
                        </details>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null,
      )}
    </>
  );
}

// ---------- our own shops ----------

export type Kind = NonNullable<CheckRow["kind"]>;

/** The words under a check that didn't pass, by state. None of them reads like a pass. */
export const KIND_WORDS: Record<Exclude<Kind, "passed">, { tag: string; line: string }> = {
  waiting: { tag: "Waiting for you", line: "Accepted, but only you can prove it reached you: tap “Yes, I got it” in the test order email." },
  failed: { tag: "Not working", line: "" },
  couldnt_check: { tag: "Couldn't check", line: "Not passed and not failed: we couldn't look this up, so we don't know yet. The problem was on our side." },
  couldnt_finish: { tag: "Couldn't finish", line: "Not passed: this check ran out of time before it had an answer. We'll try again on the next round." },
  keeps_breaking: { tag: "Keeps breaking · needs you", line: "We fixed this several times today and it broke again, so we've stopped fixing it by ourselves." },
};

export function KindTag({ kind }: { kind?: Kind }) {
  if (!kind || kind === "passed") return null;
  return <span className={`kind kind-${kind}`}>{KIND_WORDS[kind].tag}</span>;
}

/** The Doctor's investigation as a short readable timeline:
 *  "Looked up where your address leads → it leads nowhere → pointed it at your shop again → checked again: working". */
export const LOOKS: Record<string, string> = {
  resolve: "Looked up where your address leads",
  fetch: "Opened your shop page",
  evidence: "Read the proof stored for this check",
  smtp_test: "Tried signing in to our mail service (sent nothing)",
  mailbox_status: "Checked that our mailbox is active",
};
export const FIXES: Record<string, string> = {
  repoint_site: "Pointed your address at your shop again",
  retry_certificate: "Asked for a new padlock certificate",
  readd_mx: "Re-added the email settings we made",
  readd_email_auth: "Re-added the email protection settings we made",
  restore_backup: "Put your settings back as they were",
};

/** What a read-only look saw, in plain words (the technical answer stays in "Technical details"). */
export function sawPlain(tool: string, short: string): string {
  const s = short.toLowerCase();
  if (s.startsWith("refused")) return "not allowed (only your own shop can be looked at)";
  if (tool === "resolve") return s.includes("= nothing") ? "it leads nowhere" : "it leads to our server";
  if (tool === "fetch") {
    if (s.includes("shop_marker=missing")) return "a page opened, but it isn't your shop";
    if (s.includes("certificate_valid=false")) return "the padlock isn't working";
    if (s.includes("shop_marker=present")) return "your shop opened, with the padlock";
    return "it didn't open";
  }
  if (tool === "smtp_test") return s.startsWith("login refused") ? "our mail service refused our sign-in" : s.startsWith("ok") ? "sign-in worked" : "no clear answer";
  if (tool === "mailbox_status") return s.includes("active") ? "the mailbox is active" : "no clear answer";
  if (tool === "evidence") return "read";
  return "done";
}

export function DoctorTimeline({ d, passed, fixed }: { d: DoctorLook; passed: boolean; fixed: boolean }) {
  const steps: { text: string; tone?: "fix" | "ok" | "you" }[] = d.trace.map((t) => ({
    text: `${LOOKS[t.tool] ?? "Looked"} → ${sawPlain(t.tool, t.short_result)}`,
  }));
  if (d.fix_id && d.fix_id !== "needs_owner" && FIXES[d.fix_id]) steps.push({ text: FIXES[d.fix_id], tone: "fix" });
  if (fixed && passed) steps.push({ text: "Checked again: working", tone: "ok" });
  else if (d.fix_id === "needs_owner") steps.push({ text: "Needs you", tone: "you" });
  else if (!passed) steps.push({ text: "Checked again: still not working", tone: "you" });
  return (
    <div className="doctor-found">
      <div className="doctor-label">
        What we found
        {d.source === "standard" && <span className="std-fix">{d.fix_id === "needs_owner" ? "Standard answer" : "Standard fix"}</span>}
      </div>
      <p>{d.finding}</p>
      {steps.length > 0 && (
        <ol className="doctor-timeline" aria-label="What we did, in order">
          {steps.map((s, i) => (
            <li key={i} className={s.tone ? `tl-${s.tone}` : undefined}>
              {s.text}
            </li>
          ))}
        </ol>
      )}
      {d.fix_id === "needs_owner" && d.owner_instruction && <Steps text={d.owner_instruction} label="Needs you" />}
    </div>
  );
}
