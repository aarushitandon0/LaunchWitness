import { useEffect, useState } from "react";

type Health = { ok: boolean; env: string };
type State =
  | { kind: "loading" }
  | { kind: "ok"; health: Health }
  | { kind: "error"; message: string };

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    fetch("/api/health")
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const health = (await r.json()) as Health;
        setState(health.ok ? { kind: "ok", health } : { kind: "error", message: "Server says not ok" });
      })
      .catch((e: unknown) => setState({ kind: "error", message: String(e) }));
  }, []);

  return (
    <main className="page">
      <h1>LaunchWitness</h1>
      <p className="tagline">
        Describe your business. We launch it on GoDaddy and prove everything works before your first
        customer arrives.
      </p>

      <section className={`status status-${state.kind}`} aria-live="polite">
        {state.kind === "loading" && <p>Checking that LaunchWitness is running…</p>}
        {state.kind === "ok" && <p>✅ LaunchWitness is running and ready.</p>}
        {state.kind === "error" && <p>⚠️ LaunchWitness isn't responding right now. Please try again in a minute.</p>}

        <details>
          <summary>Details</summary>
          <pre>
            {state.kind === "ok" && JSON.stringify(state.health, null, 2)}
            {state.kind === "error" && state.message}
            {state.kind === "loading" && "GET /api/health …"}
          </pre>
        </details>
      </section>
    </main>
  );
}
