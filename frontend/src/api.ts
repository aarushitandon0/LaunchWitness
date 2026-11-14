export type Product = { name: string; price_inr: number; description: string; category: string };

export type Profile = {
  name: string;
  tagline: string;
  about: string;
  area: string;
  hours: string;
  phone: string;
  whatsapp: string;
  upi_id: string;
  tone: string;
  products: Product[];
};

export type Business = {
  id: number;
  subdomain: string;
  site_url: string | null;
  status: string;
  practice: boolean;
  owner_email: string;
  profile: Profile;
  owner_key?: string; // only in the response that created the business
  owner_link?: string;
};

export type BusinessSummary = { id: number; name: string; subdomain: string | null; site_url: string | null };

export type Sample = { id: string; owner_name: string; city: string; description: string; price_list: string };

export type Order = {
  id: number;
  customer_name: string;
  customer_phone: string;
  items: { name: string; qty: number; price_inr: number }[];
  total_inr: number;
  note: string;
  email_status: string;
  created_at: string;
};

export type Step = {
  id: string;
  kind: string;
  title: string;
  detail: string;
  status: "pending" | "running" | "done" | "skipped" | "failed" | "blocked";
  message: string;
  started_at: string | null;
  finished_at: string | null;
};

export type DnsChange = {
  zone: string;
  type: string;
  name: string;
  say: string;
  deferred: boolean;
  before_text: string[];
  after_text: string[];
};

export type Plan = {
  id: number;
  business_id: number;
  mode: "sandbox" | "full";
  zone: string;
  site_host: string;
  mailbox: string;
  status: "draft" | "approved" | "running" | "done" | "failed" | "blocked";
  total_cost_usd: number;
  steps: Step[];
  changes: DnsChange[];
  site_url: string | null;
  practice: boolean;
  email_plan_estimate_usd: number | null;
  approvals: { action: string; target: string; amount_usd: number; approved_by: string; used: boolean }[];
};

export type NameIdea = { domain: string; price_usd: number };

export type CheckRow = {
  check: string;
  title: string;
  passed: boolean;
  plain: string;
  detail: string;
  at: string;
  attempt: number;
  first_passed: boolean;
  fixed: boolean;
};

export type Repair = {
  check: string;
  title: string;
  fixed: boolean;
  attempts: { explanation: string; fix_id: string; applied: boolean; message: string; passed: boolean }[];
};

export type AuditRow = { at: string; actor: string; action: string; target: string; result: string; detail: string };

export type Report = {
  business: { id: number; name: string; site_url: string | null; has_owner_email: boolean; practice: boolean };
  plan: { id: number; mode: "sandbox" | "full"; site_host: string; mailbox: string } | null;
  ready: boolean;
  headline: string;
  left: string[];
  run: {
    id: number;
    trigger: string;
    status: "running" | "done";
    passed: boolean | null;
    started_at: string;
    finished_at: string | null;
    checks: CheckRow[];
    repairs: Repair[];
  } | null;
  monitoring: {
    enabled: boolean;
    every_minutes: number;
    last_quick: { at: string; passed: boolean } | null;
    last_daily: { at: string; passed: boolean } | null;
    cert_days_left: number | null;
    domain_days_left: number | null;
  };
  audit: AuditRow[];
  admin: boolean;
  demo_fault: string | null;
};

// ---- secret owner keys (one per business) and the admin token, kept in this browser only ----

const store = {
  get(k: string): string | null {
    try {
      return window.localStorage.getItem(k);
    } catch {
      return null;
    }
  },
  set(k: string, v: string | null) {
    try {
      if (v === null) window.localStorage.removeItem(k);
      else window.localStorage.setItem(k, v);
    } catch {
      /* private window: keys live only in this tab's memory */
    }
  },
};

export const keys = {
  owner: (id: number) => store.get(`lw-owner-${id}`),
  setOwner: (id: number, key: string, name?: string) => {
    store.set(`lw-owner-${id}`, key);
    const mine = keys.mine().filter((b) => b.id !== id);
    store.set("lw-mine", JSON.stringify([{ id, name: name ?? `Business ${id}` }, ...mine]));
  },
  mine: (): { id: number; name: string }[] => {
    try {
      return JSON.parse(store.get("lw-mine") ?? "[]");
    } catch {
      return [];
    }
  },
  admin: () => store.get("lw-admin"),
  setAdmin: (t: string | null) => store.set("lw-admin", t),
};

function authHeaders(businessId?: number): Record<string, string> {
  const h: Record<string, string> = {};
  const owner = businessId !== undefined ? keys.owner(businessId) : null;
  if (owner) h["X-Owner-Key"] = owner;
  const admin = keys.admin();
  if (admin) h["X-Admin-Token"] = admin;
  return h;
}

const json = (body: unknown, businessId?: number): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json", ...authHeaders(businessId) },
  body: JSON.stringify(body),
});

/** Error whose message is plain English from the server (safe to show). */
export class ApiError extends Error {
  constructor(message: string, public status: number, public details: unknown = null) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit, businessId?: number): Promise<T> {
  let r: Response;
  try {
    r = await fetch(path, { ...init, headers: { ...authHeaders(businessId), ...(init?.headers ?? {}) } });
  } catch {
    throw new ApiError("We couldn't reach LaunchWitness. Please check your internet and try again.", 0);
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : r.status === 422
          ? "Some details need fixing. Please check the highlighted fields."
          : "Something went wrong on our side. Please try again.";
    throw new ApiError(message, r.status, detail);
  }
  return body as T;
}

export const api = {
  health: () => request<{ ok: boolean; env: string }>("/api/health"),
  samples: () => request<Sample[]>("/api/samples"),
  list: () => request<BusinessSummary[]>("/api/businesses"), // admin only
  get: (id: number) => request<Business>(`/api/businesses/${id}`, undefined, id),
  orders: (id: number) => request<Order[]>(`/api/businesses/${id}/orders`, undefined, id),
  create: (description: string, priceList: string, photo: File | null) => {
    const form = new FormData();
    form.set("description", description);
    form.set("price_list", priceList);
    if (photo) form.set("photo", photo);
    return request<Business>("/api/businesses", { method: "POST", body: form });
  },
  practiceMode: () => request<{ practice: boolean; admin: boolean }>("/api/practice-mode"),
  names: (id: number) => request<NameIdea[]>(`/api/businesses/${id}/names`, undefined, id),
  plan: (bid: number, id: number) => request<Plan>(`/api/plans/${id}`, undefined, bid),
  createPlan: (businessId: number, mode: "sandbox" | "full", domain?: string) =>
    request<Plan>(`/api/businesses/${businessId}/plans`, json({ mode, domain: domain ?? null }, businessId), businessId),
  approve: (bid: number, planId: number, approvedBy: string) =>
    request<{ ok: boolean }>(`/api/plans/${planId}/approve`, json({ approved_by: approvedBy || "owner" }, bid), bid),
  resume: (bid: number, planId: number) => request<{ ok: boolean }>(`/api/plans/${planId}/resume`, { method: "POST" }, bid),
  practiceBuy: (bid: number, planId: number) =>
    request<{ ok: boolean }>(`/api/plans/${planId}/practice-buy`, { method: "POST" }, bid),
  save: (id: number, profile: Profile, subdomain: string, ownerEmail: string) =>
    request<Business>(
      `/api/businesses/${id}`,
      { ...json({ profile, subdomain, owner_email: ownerEmail }, id), method: "PUT" },
      id,
    ),
  report: (id: number) => request<Report>(`/api/businesses/${id}/report`, undefined, id),
  runChecks: (id: number) => request<{ ok: boolean; run_id: number }>(`/api/businesses/${id}/checks`, { method: "POST" }, id),
  adminCheck: (token: string) =>
    request<{ admin: boolean }>("/api/admin/check", { headers: { "X-Admin-Token": token } }),
  setDemoFault: (id: number, fault: "" | "dmarc" | "mx") =>
    request<{ ok: boolean; demo_fault: string }>(`/api/admin/businesses/${id}/demo-fault`, {
      ...json({ fault }),
      method: "PUT",
    }),
};

export const inr = (n: number) => "₹" + new Intl.NumberFormat("en-IN").format(n);

export const usd = (n: number) => "$" + n.toFixed(2);
