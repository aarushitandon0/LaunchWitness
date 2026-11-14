import { useEffect, useState } from "react";
import { api } from "./api";
import Describe from "./Describe";
import Review from "./Review";

/** Tiny hash router: "#/" = describe, "#/b/<id>" = review that business. */
function useRoute(): { businessId: number | null } {
  const parse = () => {
    const m = window.location.hash.match(/^#\/b\/(\d+)/);
    return { businessId: m ? Number(m[1]) : null };
  };
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const go = (businessId: number | null) => {
  window.location.hash = businessId === null ? "#/" : `#/b/${businessId}`;
  window.scrollTo(0, 0);
};

export default function App() {
  const { businessId } = useRoute();
  return (
    <main className="page">
      <header className="top">
        <a className="logo" href="#/">
          LaunchWitness
        </a>
      </header>
      {businessId === null ? <Describe /> : <Review key={businessId} id={businessId} />}
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
