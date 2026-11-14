import { useEffect, useState } from "react";
import { api } from "./api";
import Describe from "./Describe";
import Review from "./Review";
import { LaunchChoice, PlanView } from "./Launch";

type Route =
  | { page: "describe" }
  | { page: "review"; businessId: number }
  | { page: "launch"; businessId: number }
  | { page: "plan"; planId: number };

/** Tiny hash router: #/ · #/b/<id> · #/b/<id>/launch · #/plan/<id> */
function useRoute(): Route {
  const parse = (): Route => {
    const h = window.location.hash;
    let m = h.match(/^#\/b\/(\d+)\/launch/);
    if (m) return { page: "launch", businessId: Number(m[1]) };
    m = h.match(/^#\/b\/(\d+)/);
    if (m) return { page: "review", businessId: Number(m[1]) };
    m = h.match(/^#\/plan\/(\d+)/);
    if (m) return { page: "plan", planId: Number(m[1]) };
    return { page: "describe" };
  };
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (businessId: number | null) => goTo(businessId === null ? "#/" : `#/b/${businessId}`);

export const goTo = (hash: string) => {
  window.location.hash = hash;
  window.scrollTo(0, 0);
};

export default function App() {
  const route = useRoute();
  const [practice, setPractice] = useState(false);
  useEffect(() => {
    api.practiceMode().then((p) => setPractice(p.practice)).catch(() => setPractice(false));
  }, []);
  return (
    <main className="page">
      <header className="top">
        <a className="logo" href="#/">
          LaunchWitness
        </a>
      </header>
      {practice && (
        <p className="practice" role="note">
          Practice mode: launches run against a pretend GoDaddy. Nothing is bought and no real settings change.
        </p>
      )}
      {route.page === "describe" && <Describe />}
      {route.page === "review" && <Review key={route.businessId} id={route.businessId} />}
      {route.page === "launch" && <LaunchChoice key={route.businessId} businessId={route.businessId} />}
      {route.page === "plan" && <PlanView key={route.planId} planId={route.planId} />}
      <Health />
    </main>
  );
}

function Health() {
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [detail, setDetail] = useState("GET /api/health …");
  useEffect(() => {
    api
      .health()
      .then((h) => {
        setState(h.ok ? "ok" : "error");
        setDetail(JSON.stringify(h, null, 2));
      })
      .catch((e: unknown) => {
        setState("error");
        setDetail(String(e));
      });
  }, []);
  return (
    <footer className={`health health-${state}`} aria-live="polite">
      {state === "loading" && "Checking that LaunchWitness is running…"}
      {state === "ok" && "✅ LaunchWitness is running and ready."}
      {state === "error" && "⚠️ LaunchWitness isn't responding right now. Please try again in a minute."}
      <details>
        <summary>Details</summary>
        <pre>{detail}</pre>
      </details>
    </footer>
  );
}
