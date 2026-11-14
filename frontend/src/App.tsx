import { useEffect, useState } from "react";
import { api, keys } from "./api";
import Describe from "./Describe";
import Landing from "./Landing";
import Review from "./Review";
import { LaunchChoice, PlanView } from "./Launch";
import { AdminPage, OwnerLinkPage, ReportPage } from "./Report";

type Route =
  | { page: "home" }
  | { page: "describe" }
  | { page: "admin" }
  | { page: "saved"; businessId: number }
  | { page: "review"; businessId: number }
  | { page: "launch"; businessId: number }
  | { page: "report"; businessId: number }
  | { page: "plan"; businessId: number; planId: number };

/** Tiny hash router: #/ (landing) · #/try (describe) · #/admin · #/b/<id>[?key=…] · #/b/<id>/saved · #/b/<id>/launch · #/b/<id>/plan/<pid> · #/b/<id>/report */
function useRoute(): Route {
  const parse = (): Route => {
    let h = window.location.hash;
    // Owner link: remember the key in this browser, then drop it from the address bar.
    const k = h.match(/^#\/b\/(\d+)\?key=([A-Za-z0-9_-]+)/);
    if (k) {
      keys.setOwner(Number(k[1]), k[2]);
      h = `#/b/${k[1]}`;
      window.history.replaceState(null, "", h);
    }
    if (h.startsWith("#/admin")) return { page: "admin" };
    if (h.startsWith("#/try")) return { page: "describe" };
    let m = h.match(/^#\/b\/(\d+)\/plan\/(\d+)/);
    if (m) return { page: "plan", businessId: Number(m[1]), planId: Number(m[2]) };
    m = h.match(/^#\/b\/(\d+)\/(launch|report|saved)/);
    if (m) return { page: m[2] as "launch" | "report" | "saved", businessId: Number(m[1]) };
    m = h.match(/^#\/b\/(\d+)/);
    if (m) return { page: "review", businessId: Number(m[1]) };
    return { page: "home" };
  };
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (businessId: number | null) => goTo(businessId === null ? "#/try" : `#/b/${businessId}`);

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
      {practice && route.page !== "home" && (
        <p className="practice" role="note">
          Practice mode: launches run against a pretend GoDaddy. Nothing is bought and no real settings change.
        </p>
      )}
      {route.page === "home" && <Landing />}
      {route.page === "describe" && <Describe />}
      {route.page === "review" && <Review key={route.businessId} id={route.businessId} />}
      {route.page === "launch" && <LaunchChoice key={route.businessId} businessId={route.businessId} />}
      {route.page === "plan" && <PlanView key={route.planId} businessId={route.businessId} planId={route.planId} />}
      {route.page === "report" && <ReportPage key={route.businessId} businessId={route.businessId} />}
      {route.page === "saved" && <OwnerLinkPage key={route.businessId} businessId={route.businessId} />}
      {route.page === "admin" && <AdminPage />}
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
