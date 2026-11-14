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
  profile: Profile;
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
  approvals: { action: string; target: string; amount_usd: number; approved_by: string; used: boolean }[];
};

export type NameIdea = { domain: string; price_usd: number };

/** Error whose message is plain English from the server (safe to show). */
export class ApiError extends Error {
  constructor(message: string, public status: number, public details: unknown = null) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(path, init);
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
  list: () => request<BusinessSummary[]>("/api/businesses"),
  get: (id: number) => request<Business>(`/api/businesses/${id}`),
  orders: (id: number) => request<Order[]>(`/api/businesses/${id}/orders`),
  create: (description: string, priceList: string, photo: File | null) => {
    const form = new FormData();
    form.set("description", description);
    form.set("price_list", priceList);
    if (photo) form.set("photo", photo);
    return request<Business>("/api/businesses", { method: "POST", body: form });
  },
  practiceMode: () => request<{ practice: boolean }>("/api/practice-mode"),
  names: (id: number) => request<NameIdea[]>(`/api/businesses/${id}/names`),
  plan: (id: number) => request<Plan>(`/api/plans/${id}`),
  createPlan: (businessId: number, mode: "sandbox" | "full", domain?: string) =>
    request<Plan>(`/api/businesses/${businessId}/plans`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, domain: domain ?? null }),
    }),
  approve: (planId: number, approvedBy: string) =>
    request<{ ok: boolean }>(`/api/plans/${planId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved_by: approvedBy || "owner" }),
    }),
  resume: (planId: number) => request<{ ok: boolean }>(`/api/plans/${planId}/resume`, { method: "POST" }),
  save: (id: number, profile: Profile, subdomain: string) =>
    request<Business>(`/api/businesses/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, subdomain }),
    }),
};

export const inr = (n: number) => "₹" + new Intl.NumberFormat("en-IN").format(n);

export const usd = (n: number) => "$" + n.toFixed(2);
