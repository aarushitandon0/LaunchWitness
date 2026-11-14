import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { api, keys } from "./api";
import { EASE, useCalm } from "./motion";
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

const routeKey = (r: Route) =>
  `${r.page}-${"businessId" in r ? r.businessId : ""}-${"planId" in r ? r.planId : ""}`;

export function LogoMark() {
  return (
    <svg className="logo-mark" viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="10.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="5" fill="var(--accent)" />
      <path d="M9.6 12.1l1.6 1.6 3.2-3.3" fill="none" stroke="var(--accent-ink)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function TopBar({ page }: { page: Route["page"] }) {
  const current = (p: boolean) => (p ? ({ "aria-current": "page" } as const) : {});
  return (
    <header className="topbar">
      <a className="logo" href="#/">
        <LogoMark />
        LaunchWitness
      </a>
      <nav className="notch" aria-label="Main">
        <a href="#/" {...current(page === "home")}>
          Home
        </a>
        <a href="#/try" {...current(page === "describe")}>
          Describe
        </a>
        <a href="/build">Build log</a>
        {page === "home" && <a href="#contact">Contact</a>}
      </nav>
      <div className="topbar-end">
        {page !== "describe" && (
          <a className="pill-cta" href="#/try">
            Try it
          </a>
        )}
      </div>
    </header>
  );
}

export default function App() {
  const route = useRoute();
  const calm = useCalm();
  const [practice, setPractice] = useState(false);
  useEffect(() => {
    api.practiceMode().then((p) => setPractice(p.practice)).catch(() => setPractice(false));
  }, []);
  const home = route.page === "home";
  const enter = calm ? { opacity: 0 } : { opacity: 0, y: 14 };
  const leave = calm ? { opacity: 0 } : { opacity: 0, y: -8 };
  return (
    <div className="frame with-notch">
      <TopBar page={route.page} />
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={home ? "home" : "app"}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25, ease: EASE }}
          style={{ flex: 1, display: "flex", flexDirection: "column" }}
        >
          {home ? (
            <>
              <Landing />
              <Health dark />
            </>
          ) : (
            <div className="sheet">
              <main className="page">
                {practice && (
                  <p className="practice" role="note">
                    Practice mode: launches run against a pretend GoDaddy. Nothing is bought and no real settings change.
                  </p>
                )}
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={routeKey(route)}
                    initial={enter}
                    animate={{ opacity: 1, y: 0 }}
                    exit={leave}
                    transition={{ duration: 0.35, ease: EASE }}
                  >
                    {route.page === "describe" && <Describe />}
                    {route.page === "review" && <Review key={route.businessId} id={route.businessId} />}
                    {route.page === "launch" && <LaunchChoice key={route.businessId} businessId={route.businessId} />}
                    {route.page === "plan" && (
                      <PlanView key={route.planId} businessId={route.businessId} planId={route.planId} />
                    )}
                    {route.page === "report" && <ReportPage key={route.businessId} businessId={route.businessId} />}
                    {route.page === "saved" && <OwnerLinkPage key={route.businessId} businessId={route.businessId} />}
                    {route.page === "admin" && <AdminPage />}
                  </motion.div>
                </AnimatePresence>
              </main>
              <Health />
            </div>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function Health({ dark = false }: { dark?: boolean }) {
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
    <footer className={`health health-${state}${dark ? " landing-footer" : ""}`} aria-live="polite">
      <span className="health-text">
        {state === "loading" && "Checking that LaunchWitness is running…"}
        {state === "ok" && "LaunchWitness is running and ready."}
        {state === "error" && "LaunchWitness isn't responding right now. Please try again in a minute."}
      </span>
      <details>
        <summary>Details</summary>
        <pre>{detail}</pre>
      </details>
    </footer>
  );
}
