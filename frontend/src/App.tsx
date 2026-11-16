import { AnimatePresence, motion } from "framer-motion";
import { ReactNode, useEffect, useState } from "react";
import { api } from "./api";
import { EASE, useCalm } from "./motion";
import Describe from "./Describe";
import Landing from "./Landing";
import Review from "./Review";
import { LaunchChoice, PlanView } from "./Launch";
import { GotItPage, ReportPage } from "./Report";
import { OrdersPage } from "./Orders";
import { AdminPage } from "./Admin";
import { LegalLinks, PrivacyPage, TermsPage } from "./Legal";
import {
  AccountPage,
  ConfirmSignInPage,
  DeleteAccountPage,
  GuestNote,
  MyShopsPage,
  PendingNote,
  SignInPage,
  useMe,
} from "./Account";

type Route =
  | { page: "home" }
  | { page: "new" } // describe, signed in
  | { page: "try" } // describe without an account: guest practice
  | { page: "admin" }
  | { page: "signin" }
  | { page: "confirm" }
  | { page: "shops" }
  | { page: "account" }
  | { page: "delete-account" }
  | { page: "got-it" }
  | { page: "privacy" }
  | { page: "terms" }
  | { page: "notfound" }
  | { page: "review"; businessId: number }
  | { page: "launch"; businessId: number }
  | { page: "orders"; businessId: number }
  | { page: "report"; businessId: number }
  | { page: "plan"; businessId: number; planId: number };

/** Hash router. Every page has its own URL, so Back/Forward, refresh and deep links work:
 * #/ (landing; #check, #contact etc. are in-page anchors) · #/new (describe) · #/try (describe, no account) ·
 * #/signin[?next=] · #/signin/confirm?token= · #/shops · #/account · #/account/delete?token= · #/admin ·
 * #/b/<id> (review) · #/b/<id>/launch (name) · #/b/<id>/plan/<pid> (approve + launch) · #/b/<id>/report ·
 * #/b/<id>/orders · #/got-it?token= · #/privacy · #/terms. Anything else under #/ is "Page not found". */
export function parseRoute(hash: string): Route {
  if (!hash.startsWith("#/")) return { page: "home" }; // "", "#", or an in-page anchor of the landing page
  const path = hash.slice(1).split("?")[0].replace(/\/+$/, "") || "/";
  const fixed: Record<string, Route["page"]> = {
    "/": "home",
    "/new": "new",
    "/try": "try",
    "/admin": "admin",
    "/signin": "signin",
    "/signin/confirm": "confirm",
    "/shops": "shops",
    "/account": "account",
    "/account/delete": "delete-account",
    "/got-it": "got-it",
    "/privacy": "privacy",
    "/terms": "terms",
  };
  if (path in fixed) return { page: fixed[path] } as Route;
  let m = path.match(/^\/b\/(\d+)\/plan\/(\d+)$/);
  if (m) return { page: "plan", businessId: Number(m[1]), planId: Number(m[2]) };
  m = path.match(/^\/b\/(\d+)\/(launch|report|orders)$/);
  if (m) return { page: m[2] as "launch" | "report" | "orders", businessId: Number(m[1]) };
  m = path.match(/^\/b\/(\d+)$/);
  if (m) return { page: "review", businessId: Number(m[1]) };
  return { page: "notfound" };
}

function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

/** Go somewhere without adding a history entry (used by the convenience guards, so Back still works). */
export const replaceTo = (hash: string) => window.location.replace(hash);

const TITLES: Partial<Record<Route["page"], string>> = {
  home: "LaunchWitness",
  new: "Describe your business",
  try: "Try it without an account",
  signin: "Sign in",
  confirm: "Sign in",
  shops: "My shops",
  account: "Account",
  admin: "Team",
  review: "Check your details",
  launch: "Choose an address",
  plan: "Approve and launch",
  report: "Launch report",
  orders: "Orders",
  privacy: "Privacy",
  terms: "Terms",
  notfound: "Page not found",
};

export const go = (businessId: number | null) => goTo(businessId === null ? "#/new" : `#/b/${businessId}`);

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

const SHOP_PAGES: Route["page"][] = ["shops", "review", "launch", "plan", "report", "orders"];

function NavLinks({ page }: { page: Route["page"] }) {
  const me = useMe();
  const current = (p: boolean) => (p ? ({ "aria-current": "page" } as const) : {});
  if (me?.user)
    return (
      <>
        <a href="#/shops" {...current(SHOP_PAGES.includes(page))}>
          My shops
        </a>
        <a href="#/new" {...current(page === "new" || page === "try")}>
          New shop
        </a>
        <a href="#/account" {...current(page === "account" || page === "delete-account")}>
          Account
        </a>
        {me.user.role === "admin" && (
          <a href="#/admin" {...current(page === "admin")}>
            Team
          </a>
        )}
      </>
    );
  return (
    <>
      <a href="#/" {...current(page === "home")}>
        Home
      </a>
      <a href="/demo/meera">See a demo shop</a>
      {me?.guest && (
        <a href="#/shops" {...current(SHOP_PAGES.includes(page))}>
          My practice shops
        </a>
      )}
      <a href="#/signin" {...current(page === "signin" || page === "confirm")}>
        Sign in
      </a>
    </>
  );
}

function TopBar({ page }: { page: Route["page"] }) {
  const me = useMe();
  const signedIn = !!me?.user;
  return (
    <>
      <header className="topbar">
        <a className="logo" href={signedIn ? "#/shops" : "#/"}>
          <LogoMark />
          LaunchWitness
        </a>
        <nav className="notch" aria-label="Main">
          <NavLinks page={page} />
        </nav>
        <div className="topbar-end">
          {!signedIn && !["new", "try", "signin", "confirm"].includes(page) && (
            <a className="pill-cta" href="#/new">
              Start
            </a>
          )}
        </div>
      </header>
      <nav className="mobile-nav" aria-label="Main (small screens)">
        <NavLinks page={page} />
      </nav>
    </>
  );
}

/** Convenience only: the server still decides. Sends a signed-out visitor to sign in, and back here afterwards. */
function NeedsSignIn({ next, children }: { next: string; children: ReactNode }) {
  const me = useMe();
  const out = me !== null && !me.user;
  useEffect(() => {
    if (out) replaceTo(`#/signin?next=${encodeURIComponent(next)}`);
  }, [out, next]);
  if (!me || out) return <p>Loading…</p>;
  return <>{children}</>;
}

function GoTo({ hash }: { hash: string }) {
  useEffect(() => replaceTo(hash), [hash]);
  return <p>Loading…</p>;
}

export function NotFoundPage() {
  return (
    <>
      <p className="eyebrow">404</p>
      <h1>Page not found</h1>
      <p className="tagline">There's no page at this address. It may have moved, or the link may be cut short.</p>
      <div className="actions">
        <a className="btn btn-primary" href="#/shops">
          Back to My shops
        </a>
        <a className="btn btn-ghost" href="#/">
          Home
        </a>
      </div>
    </>
  );
}

export default function App() {
  const route = useRoute();
  const calm = useCalm();
  const me = useMe();
  const practice = !!me?.practice_server;
  const shopPage = "businessId" in route;
  const home = route.page === "home";
  // The practice-server note matters only where something is launched or reported.
  const showPractice = practice && ["new", "try", "launch", "plan", "report"].includes(route.page);
  useEffect(() => {
    document.title = route.page === "home" ? "LaunchWitness" : `${TITLES[route.page] ?? "LaunchWitness"} · LaunchWitness`;
  }, [route.page]);
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
                {showPractice && (
                  <p className="practice practice-mini" role="note">
                    Practice server: launches here use a pretend GoDaddy. Nothing is bought and no real settings change.
                  </p>
                )}
                {shopPage && me && !me.user && <GuestNote />}
                {shopPage && me?.user?.status === "pending" && <PendingNote />}
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={routeKey(route)}
                    initial={enter}
                    animate={{ opacity: 1, y: 0 }}
                    exit={leave}
                    transition={{ duration: 0.35, ease: EASE }}
                  >
                    {route.page === "new" && (
                      <NeedsSignIn next="new">
                        <Describe />
                      </NeedsSignIn>
                    )}
                    {route.page === "try" && (me?.user ? <GoTo hash="#/new" /> : <Describe guest />)}
                    {route.page === "review" && <Review key={route.businessId} id={route.businessId} />}
                    {route.page === "launch" && <LaunchChoice key={route.businessId} businessId={route.businessId} />}
                    {route.page === "plan" && (
                      <PlanView key={route.planId} businessId={route.businessId} planId={route.planId} />
                    )}
                    {route.page === "report" && <ReportPage key={route.businessId} businessId={route.businessId} />}
                    {route.page === "orders" && <OrdersPage key={route.businessId} businessId={route.businessId} />}
                    {route.page === "admin" && <AdminPage />}
                    {route.page === "signin" && <SignInPage />}
                    {route.page === "confirm" && <ConfirmSignInPage />}
                    {route.page === "shops" && <MyShopsPage />}
                    {route.page === "account" && (
                      <NeedsSignIn next="account">
                        <AccountPage />
                      </NeedsSignIn>
                    )}
                    {route.page === "delete-account" && <DeleteAccountPage />}
                    {route.page === "got-it" && <GotItPage />}
                    {route.page === "privacy" && <PrivacyPage />}
                    {route.page === "terms" && <TermsPage />}
                    {route.page === "notfound" && <NotFoundPage />}
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
      <LegalLinks />
      <details>
        <summary>Details</summary>
        <pre>{detail}</pre>
      </details>
    </footer>
  );
}
