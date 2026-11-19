import { useCallback, useEffect, useState } from "react";
import { AdminShop, AdminUser, api, ApiError, OutboxSummary, ShopReportRow, ZoneFinding } from "./api";
import { useMe } from "./Account";
import { ErrorBox } from "./Describe";

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" }) : "—");

/** Asks for a reason, then runs the action. Kept simple: a native prompt works on every phone. */
const withReason = (question: string, fn: (reason: string) => Promise<unknown>) => async () => {
  const reason = window.prompt(question, "");
  if (reason === null) return;
  await fn(reason.trim());
};

export function AdminPage() {
  const me = useMe();
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [shops, setShops] = useState<AdminShop[] | null>(null);
  const [reports, setReports] = useState<ShopReportRow[] | null>(null);
  const [zone, setZone] = useState<ZoneFinding[] | null>(null);
  const [mail, setMail] = useState<OutboxSummary | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    Promise.all([api.admin.users(), api.admin.shops(), api.admin.reports(), api.admin.zoneFindings(), api.admin.outbox()])
      .then(([u, s, r, z, m]) => {
        setUsers(u);
        setShops(s);
        setReports(r);
        setZone(z);
        setMail(m);
      })
      .catch(setError);
  }, []);

  useEffect(() => {
    if (me?.user?.role === "admin") load();
  }, [me, load]);

  const act = (fn: () => Promise<unknown>) => async () => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e), 0));
    } finally {
      setBusy(false);
    }
  };

  if (!me) return <p>Loading…</p>;
  if (me.user?.role !== "admin")
    return (
      <>
        <h1>Team</h1>
        <p>This page is for the LaunchWitness team. {me.user ? "" : <a href="#/signin?next=admin">Sign in</a>}</p>
      </>
    );

  const queue = (users ?? []).filter((u) => u.status === "pending");
  return (
    <>
      <p className="eyebrow">Team</p>
      <h1>Team page</h1>
      {error && <ErrorBox error={error} />}

      <h2>Waiting for approval ({queue.length})</h2>
      {queue.length === 0 ? (
        <p className="muted">Nobody is waiting.</p>
      ) : (
        <ul className="names admin-list">
          {queue.map((u) => (
            <li key={u.id}>
              <span>
                <strong>{u.email}</strong>
                <br />
                <span className="muted">
                  Joined {day(u.created_at)} · {u.shops.length ? u.shops.join(", ") : "no shops yet"}
                </span>
              </span>
              <span className="actions">
                <button className="btn btn-primary btn-sm" disabled={busy} onClick={act(() => api.admin.approve(u.id))}>
                  Approve
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={busy}
                  onClick={act(withReason("Why? (the seller sees this)", (r) => api.admin.reject(u.id, r)))}
                >
                  Reject
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <h2>Reports from visitors ({reports?.length ?? 0})</h2>
      {(reports ?? []).length === 0 ? (
        <p className="muted">No open reports.</p>
      ) : (
        <ul className="names admin-list">
          {(reports ?? []).map((r) => (
            <li key={r.id}>
              <span>
                <strong>{r.shop}</strong> <span className="muted">({r.reason})</span>
                <br />
                <span className="muted">
                  {day(r.created_at)}
                  {r.note ? ` · “${r.note}”` : ""}
                  {r.paused ? " · shop paused" : ""}
                </span>
              </span>
              <span className="actions">
                {!r.paused && (
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={busy}
                    onClick={act(withReason("Why pause it?", (why) => api.admin.pause(r.business_id, why)))}
                  >
                    Pause shop
                  </button>
                )}
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={busy}
                  onClick={act(withReason("Note for closing", (why) => api.admin.closeReport(r.id, why)))}
                >
                  Close
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <h2>Email outbox</h2>
      <p className="muted">
        Every email is saved first, then sent; if the mail server is slow or down we keep trying (about 2 hours), then
        give up and show it here. Sign-in links and orders are never held back by the daily limit.
      </p>
      {mail && (
        <section className="card" aria-label="Email outbox">
          <p>
            Sent today: {mail.sent_today} of {mail.daily_limit} · waiting: {mail.counts.queued} · sending:{" "}
            {mail.counts.sending} · retrying: {mail.counts.failed} · gave up: {mail.counts.dead} · sent in all:{" "}
            {mail.counts.sent}
          </p>
          {mail.recent_errors.length > 0 && (
            <details>
              <summary>Last errors ({mail.recent_errors.length})</summary>
              <ul className="muted">
                {mail.recent_errors.map((e) => (
                  <li key={e.id}>
                    #{e.id} {e.kind}: {e.status}, {e.attempts} tr{e.attempts === 1 ? "y" : "ies"}, {e.error} (
                    {new Date(e.at).toLocaleString()})
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}

      <h2>Address records ({(zone ?? []).filter((z) => z.status === "open").length} to look at)</h2>
      <p className="muted">
        Once a day we compare the shop address records on our domain with the shops here. Nothing changes until you
        approve a fix. Only shop records are ever touched (never @, www or mail records).
      </p>
      <p>
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={act(() => api.admin.zoneCheck())}>
          Check now
        </button>
      </p>
      {(zone ?? []).filter((z) => z.status === "open").length === 0 ? (
        <p className="muted">Everything matches.</p>
      ) : (
        <ul className="names admin-list">
          {(zone ?? [])
            .filter((z) => z.status === "open")
            .map((z) => (
              <li key={z.id}>
                <span>
                  <strong>{z.name}</strong> <span className="muted">({z.kind.replace("_", " ")})</span>
                  <br />
                  <span className="muted">{z.plain}</span>
                  <details>
                    <summary>Details</summary>
                    <code>
                      A {z.name}: now [{z.found || "none"}] → after [{z.want || "removed"}]
                    </code>
                  </details>
                </span>
                <span className="actions">
                  <button className="btn btn-primary btn-sm" disabled={busy} onClick={act(() => api.admin.zoneApprove(z.id))}>
                    {z.fix === "delete" ? "Remove record" : "Point it here"}
                  </button>
                  <button className="btn btn-ghost btn-sm" disabled={busy} onClick={act(() => api.admin.zoneDismiss(z.id))}>
                    Leave it
                  </button>
                </span>
              </li>
            ))}
        </ul>
      )}

      <h2>Shops ({shops?.length ?? 0})</h2>
      <ul className="names admin-list">
        {(shops ?? []).map((b) => (
          <li key={b.id}>
            <span>
              <strong>{b.name}</strong>{" "}
              <span className="muted">
                {b.public ? "live" : b.guest ? "guest practice" : b.practice ? "practice" : b.status}
                {b.paused ? " · paused" : ""}
                {b.review === "held" ? ` · held: ${b.review_reason}` : ""}
              </span>
              {b.pending_edit && (
                <>
                  <br />
                  <span className="warn">Edited live shop: needs a look. {b.pending_edit.reason}</span>
                </>
              )}
              <br />
              <span className="muted">{b.owners.join(", ") || "no owner"}</span>
            </span>
            <span className="actions">
              {b.paused ? (
                <button className="btn btn-ghost btn-sm" disabled={busy} onClick={act(() => api.admin.unpause(b.id))}>
                  Unpause
                </button>
              ) : (
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={busy}
                  onClick={act(withReason("Why pause it?", (why) => api.admin.pause(b.id, why)))}
                >
                  Pause
                </button>
              )}
              {b.pending_edit && (
                <>
                  <a className="btn btn-ghost btn-sm" href={`#/b/${b.id}`}>
                    See the edit
                  </a>
                  <button className="btn btn-ghost btn-sm" disabled={busy} onClick={act(() => api.admin.publishEdit(b.id))}>
                    Publish edit
                  </button>
                  <button className="btn btn-ghost btn-sm" disabled={busy} onClick={act(() => api.admin.discardEdit(b.id))}>
                    Discard edit
                  </button>
                </>
              )}
              {b.review === "held" && (
                <button className="btn btn-ghost btn-sm" disabled={busy} onClick={act(() => api.admin.clearReview(b.id))}>
                  Clear review
                </button>
              )}
              <a className="btn btn-ghost btn-sm" href={`#/b/${b.id}/report`}>
                Report
              </a>
            </span>
          </li>
        ))}
      </ul>

      <h2>Accounts ({users?.length ?? 0})</h2>
      <ul className="names admin-list">
        {(users ?? []).map((u) => (
          <li key={u.id}>
            <span>
              <strong>{u.email}</strong>{" "}
              <span className="muted">
                {u.status}
                {u.role === "admin" ? " · team" : ""} · last signed in {day(u.last_login_at)}
              </span>
            </span>
            {u.role !== "admin" && u.status !== "suspended" && u.status !== "deleted" && (
              <button
                className="btn btn-ghost btn-sm"
                disabled={busy}
                onClick={act(withReason("Why suspend? (signs them out everywhere)", (r) => api.admin.suspend(u.id, r)))}
              >
                Suspend
              </button>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
