export type Product = {
  name: string;
  price_inr: number;
  description: string;
  category: string;
  addon: boolean; // an extra on top of another item
  price_from: boolean; // shown as "from ₹X"
  food_mark: "" | "veg" | "egg" | "nonveg"; // the Reader may suggest it; she confirms it
  new_until?: string; // S19D: "YYYY-MM-DD" while shown as New (the server keeps at most 15 days ahead)
};

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
  selling_point: string;
  min_notice_days: number;
  pickup_available: boolean;
  delivery_available: boolean;
  delivery_fee_inr: number;
  allow_item_message: boolean;
  upi_display_name: string;
  fssai_number: string;
  kind: "orders" | "appointments";
  not_supported_reason: string;
  instagram: string; // handle only
  delivery_areas: string;
  niche: "" | "food" | "handmade" | "custom";
  theme: string; // a key from /api/themes ("" = the suggested look)
  accent: string;
  motif: string; // S20 signature keys ("" = chosen from the shop's name)
  art: string;
  section_copy: { hero_line: string; about: string; how_ordering: string };
  testimonials: { name: string; text: string }[]; // real comments she pasted: never written by us
  // S15: where she sells, when, and how she is paid
  selling_mode: "" | "pickup" | "local" | "pickup_local" | "india" | "pickup_india";
  city: string;
  free_delivery_above_inr: number;
  shipping_fee_inr: number;
  dispatch_days: number;
  shipping_note: string;
  payment_terms: "upfront" | "advance" | "on_delivery";
  advance_percent: number;
  accepts_cash: boolean;
  cancellation_preset: "" | "no_custom" | "full_24h" | "advance_kept_48h" | "custom";
  cancellation_text: string;
  allergens: string;
  on_break: boolean;
  back_on: string; // YYYY-MM-DD or ""
  days_off: number[]; // Monday = 0
  time_slots: string[];
  max_orders_per_day: number;
};

export type ThemeAccent = { key: string; label: string; color: string; ink: string; tint: string };
export type ThemeInfo = {
  key: string;
  label: string;
  blurb: string;
  for_whom: string;
  hero: string;
  menu: string;
  tokens: { bg: string; paper: string; ink: string; ink2: string; soft: string; line: string; radius: string };
  display: string;
  body: string;
  art: string;
  accents: ThemeAccent[];
};
export type SignatureOption = { key: string; label: string; svg: string }; // svg: drawn by our own code from numbers only
export type ThemeChoice = {
  key: string;
  accent: string;
  suggested: string;
  chosen: boolean;
  motif: string; // S20: the shop's signature (picked from its name unless she chose)
  art: string;
  motif_chosen: boolean;
  art_chosen: boolean;
  motifs: SignatureOption[];
  arts: SignatureOption[];
};

export type GoLiveItem = { key: string; label: string; done: boolean; hint: string };

export type GoLive = {
  ready: boolean;
  items: GoLiveItem[];
  whatsapp: string;
  whatsapp_test_url: string | null;
  upi_test: { uri: string; qr_svg: string; name: string } | null;
  confirmed: {
    whatsapp_at: string | null;
    upi_at: string | null;
    own_goods_at: string | null;
    terms_at: string | null;
    previewed_at: string | null;
  };
};

export type ZoneFinding = {
  id: number;
  kind: "dangling" | "missing" | "wrong_target";
  name: string;
  found: string;
  want: string;
  fix: "delete" | "set";
  plain: string;
  status: "open" | "fixed" | "dismissed" | "gone";
  result: string;
  business_id: number | null;
  created_at: string;
  decided_by: string;
};

export type Renewal = {
  what: "certificate" | "domain" | "mailbox";
  label: string;
  days_left: number | null;
  state: "ok" | "soon" | "urgent" | "lapsed" | "unknown";
  who: "automatic" | "you" | "team";
  plain: string;
};

export type Business = {
  renewal?: Renewal | null; // My shops: the renewal that needs attention soonest
  new_orders?: number; // My shops: customer orders still "New"
  latest_plan: { id: number; status: Plan["status"]; practice: boolean } | null; // resume the 5-step flow here
  id: number;
  name: string;
  subdomain: string;
  site_url: string | null;
  status: string;
  practice: boolean;
  theme: ThemeChoice;
  public: boolean; // false = only the owner sees it (preview)
  live_url: string | null;
  pending_edit: { reason: string; at: string | null } | null; // S19D: her edit waits for the team; the shop shows the last approved one
  confirm_new: ("whatsapp" | "upi")[]; // S19D: changed on a live shop; customers see the old one until she confirms // S19D: a real launched shop's public address (also when paused); null = preview only
  guest: boolean; // made without signing in: practice only, removed after 24 hours
  paused: boolean;
  review: string; // "" | "ok" | "held" | "cleared"
  review_reason: string;
  owner_email: string; // the sign-in address orders and alerts go to ("" for a guest shop)
  profile: Profile;
  csrf?: string; // only when this reply also started a new guest workspace
  assistant_note?: string | null; // set when live Claude was resting and a saved sample was used
  description?: string; // S17: her own words, for Describe again
  price_list?: string;
};

export type BusinessSummary = Business;

export type Me = {
  user: { email: string; status: "pending" | "approved" | "suspended" | "deleted"; role: string; status_reason: string } | null;
  guest: boolean;
  csrf: string | null;
  practice_server: boolean; // true: every launch here runs against the pretend GoDaddy
  limits: { shops: number };
  kept_shops?: number;
};

export type AdminUser = {
  id: number;
  email: string;
  status: string;
  role: string;
  status_reason: string;
  created_at: string | null;
  last_login_at: string | null;
  shops: string[];
};

export type AdminShop = {
  id: number;
  name: string;
  subdomain: string | null;
  status: string;
  practice: boolean;
  public: boolean;
  paused: boolean;
  paused_reason: string;
  review: string;
  review_reason: string;
  guest: boolean;
  owners: string[];
  site_url: string | null;
  created_at: string | null;
  pending_edit: { reason: string; at: string | null } | null; // S19D: a held edit to a live shop
};

export type ShopReportRow = {
  id: number;
  business_id: number;
  shop: string;
  subdomain: string | null;
  paused: boolean;
  reason: string;
  note: string;
  status: string;
  created_at: string | null;
};

export type Sample = { id: string; owner_name: string; city: string; description: string; price_list: string };

export type OrderStatus = "new" | "confirmed" | "paid" | "done" | "cancelled";

export type Order = {
  id: number;
  ref: string;
  status: OrderStatus;
  next_statuses: OrderStatus[];
  whatsapp_url: string | null; // wa.me link to the CUSTOMER, message ready-typed; nothing is sent by us
  tel_url: string | null;
  customer_name: string;
  customer_phone: string;
  items: { name: string; qty: number; price_inr: number }[];
  total_inr: number;
  note: string;
  email_status: string;
  created_at: string;
  // S15: shown to the owner only
  fulfilment: "" | "pickup" | "delivery";
  delivery_address: string;
  delivery_pin: string;
  wanted_date: string;
  time_slot: string;
  fee_inr: number;
  pay_now_inr: number;
  pay_later_inr: number;
  payment_terms: string;
  payment_label: string; // "Advance paid · ₹300 due on delivery"
  paid_action: string; // what the "paid" button says
  // S20: what the customer SAID about paying (a claim, never "paid"); screenshot served to the owner only
  payment_claim: { utr: string; says: string; has_screenshot: boolean; at: string } | null;
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
  public: boolean;
  email_plan_estimate_usd: number | null;
  approvals: { action: string; target: string; amount_usd: number; approved_by: string; used: boolean }[];
};

export type NameIdea = { domain: string; price_usd: number };

export type DoctorLook = {
  finding: string;
  fix_id: string; // a playbook fix that was applied automatically, or "needs_owner"
  owner_instruction: string;
  source: "assistant" | "standard"; // "standard" = Claude was away; plain rules decided
  trace: { tool: string; args: Record<string, unknown>; short_result: string }[]; // read-only looks, in order
};

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
  waiting?: boolean;
  unfinished?: boolean;
  kind?: "passed" | "waiting" | "failed" | "couldnt_check" | "couldnt_finish" | "keeps_breaking"; // S12: one state, one wording
  sure?: "seen" | "not_seen" | "couldnt_check";
  state?: "proven" | "needs_you" | "failed"; // from stored evidence only
  doctor?: DoctorLook | null; // S11: what the Doctor found for this check, and what it looked at first
  hops?: Hop[];
};

/** One proven hop, as stored (e.g. "Form accepted" at 14:02:11, by which server). */
export type Hop = {
  step: string;
  title: string;
  at: string;
  source: string;
  server: string;
  message_id: string;
  status_code: number | null;
  cert_not_after: string | null;
  answer: string;
  practice: boolean;
};

export type AddressResult = {
  check: string;
  ok: boolean | null; // true good · false a real problem · null a note or "not sure"
  plain: string;
  detail: string; // technical: only inside "Technical details"
  sure?: "seen" | "not_seen" | "couldnt_check";
  code?: string;
  steps?: string; // that email service's own steps, plain words
  action?: "explain" | "none";
  domain?: string;
  provider?: string;
  provider_label?: string; // "Google Workspace (Gmail)"; "" when we don't recognise the service
};

/** S12: one entry of a shop's incident timeline (failure → investigation → fix → re-check), from stored rows. */
export type Incident = {
  check: string;
  title: string;
  status: "open" | "fixed" | "needs_you" | "keeps_breaking";
  opened_at: string | null;
  closed_at: string | null;
  steps: { at: string | null; what: string }[];
  next?: string; // the owner's exact next step (never on the shared page)
};

/** S12: a product photo, already re-encoded on the server (WebP, two widths, nothing of the original file kept). */
export type PhotoOut = {
  id: number;
  item: string;
  alt: string;
  small: string;
  large: string;
  small_w: number;
  small_h: number;
  large_w: number;
  large_h: number;
};
export type PhotoList = {
  shop: PhotoOut[];
  items: Record<string, PhotoOut>;
  max_shop: number;
  max_mb: number;
  matched?: string[]; // after an upload: the item(s) it went to
};

export type DemoFaultName = "" | "dmarc" | "mx" | "a_record" | "smtp_login" | "cert" | "marker";

export type Watch = { id: number; address: string; problems: string[]; results: AddressResult[]; last_checked_at: string | null };

export type Repair = {
  check: string;
  title: string;
  fixed: boolean;
  attempts: { explanation: string; fix_id: string; applied: boolean; message: string; passed: boolean }[];
};

export type AuditRow = { at: string; actor: string; action: string; target: string; result: string; detail: string };

export type Report = {
  business: { id: number; name: string; site_url: string | null; has_owner_email: boolean; practice: boolean; public: boolean };
  practice: boolean; // results come from the pretend world: always labelled
  launch: { status: string; steps: { title: string; status: string; message: string; finished_at: string | null }[] } | null;
  plan: { id: number; mode: "sandbox" | "full"; site_host: string; mailbox: string } | null;
  ready: boolean;
  headline: string;
  left: string[];
  proof: { proven: number; total: number; needs_you: number; last_checked_at: string | null; stale: boolean };
  run: {
    id: number;
    trigger: string;
    status: "running" | "done";
    passed: boolean | null;
    started_at: string;
    finished_at: string | null;
    checks: CheckRow[];
    repairs: Repair[];
    info?: { waiting_for?: string };
  } | null;
  monitoring: {
    enabled: boolean;
    every_minutes: number;
    last_quick: { at: string; passed: boolean } | null;
    last_daily: { at: string; passed: boolean } | null;
    // S13b: the daily look through 8.8.8.8 / 1.1.1.1 / 9.9.9.9 (information only, never an alert)
    public_resolvers?: { at: string | null; title: string; agree: boolean; answer: string; practice: boolean } | null;
    cert_days_left: number | null;
    domain_days_left: number | null;
  };
  renewals: Renewal[] | null;
  audit: AuditRow[];
  admin: boolean;
  demo_fault: string | null;
  confirmed_by_you: { what: "whatsapp" | "upi" | "got_it"; label: string; at: string | null }[];
  incidents: Incident[];
  symptoms_left: number;
};

// ---- who is signed in. The cookies are HttpOnly; the CSRF token comes from /api/auth/me ----
// (or from the reply that started a guest workspace) and is sent back on every change.

let csrf: string | null = null;
let meCache: Promise<Me> | null = null;
const listeners = new Set<(me: Me) => void>();

export const session = {
  /** The current account (cached; `refresh` asks the server again). */
  me(refresh = false): Promise<Me> {
    if (!meCache || refresh) {
      const p = request<Me>("/api/auth/me").then((m) => {
        csrf = m.csrf;
        listeners.forEach((f) => f(m));
        return m;
      });
      p.catch(() => {
        if (meCache === p) meCache = null;
      });
      meCache = p;
    }
    return meCache;
  },
  set(m: Me) {
    csrf = m.csrf;
    meCache = Promise.resolve(m);
    listeners.forEach((f) => f(m));
  },
  onChange(f: (me: Me) => void) {
    listeners.add(f);
    return () => {
      listeners.delete(f);
    };
  },
};

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

const json = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** Error whose message is plain English from the server (safe to show). */
export class ApiError extends Error {
  constructor(message: string, public status: number, public details: unknown = null) {
    super(message);
  }
}

/** Friendly note from the last API response when the assistant fell back to a saved sample (else null). */
export let lastAssistantNote: string | null = null;

/** Pages that work without signing in. A 401 anywhere else sends the person to sign in. */
const OPEN_PAGES = /^#\/(try|new|signin.*|check|got-it|privacy|terms)?$/;

function toSignIn() {
  const here = window.location.hash || "#/";
  if (OPEN_PAGES.test(here.split("?")[0])) return;
  window.location.hash = `#/signin?next=${encodeURIComponent(here.slice(2))}`;
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = { ...((init?.headers as Record<string, string>) ?? {}) };
  if (UNSAFE.has(method) && path.startsWith("/api/")) {
    if (csrf === null) await session.me().catch(() => null);
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  try {
    return await fetch(path, { ...init, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError("We couldn't reach LaunchWitness. Please check your internet and try again.", 0);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await send(path, init);
  lastAssistantNote = r.headers.get("X-Assistant-Note");
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : r.status === 422
          ? "Some details need fixing. Please check the highlighted fields."
          : "Something went wrong on our side. Please try again.";
    if (r.status === 401 && path !== "/api/auth/me") toSignIn();
    throw new ApiError(message, r.status, detail);
  }
  return body as T;
}

export const api = {
  health: () => request<{ ok: boolean; env: string }>("/api/health"),
  samples: () => request<Sample[]>("/api/samples"),
  // ---- account ----
  me: () => session.me(true),
  requestLink: (email: string, next?: string) =>
    request<{ ok: boolean; message: string; dev_link?: string; mail_delayed?: boolean }>("/api/auth/request-link", json({ email, next: next ?? null })),
  confirm: async (token: string) => {
    const m = await request<Me>("/api/auth/confirm", json({ token }));
    session.set(m);
    return m;
  },
  logout: async () => {
    await request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
    return session.me(true);
  },
  logoutAll: async () => {
    const r = await request<{ ok: boolean; ended: number }>("/api/auth/logout-all", { method: "POST" });
    await session.me(true);
    return r;
  },
  deleteRequest: () =>
    request<{ ok: boolean; message: string; dev_link?: string }>("/api/account/delete-request", { method: "POST" }),
  deleteAccount: async (token: string) => {
    const r = await request<{ ok: boolean }>("/api/account/delete", json({ token }));
    await session.me(true);
    return r;
  },
  // ---- shops (only ever the caller's own) ----
  list: () => request<BusinessSummary[]>("/api/businesses"),
  get: (id: number) => request<Business>(`/api/businesses/${id}`),
  orders: (id: number) => request<Order[]>(`/api/businesses/${id}/orders`),
  golive: (id: number) => request<GoLive>(`/api/businesses/${id}/golive`),
  confirmCheck: (id: number, what: "whatsapp" | "upi" | "agreements", extra: { own_goods?: boolean; terms?: boolean } = {}) =>
    request<GoLive>(`/api/businesses/${id}/confirm`, json({ what, ...extra })),
  setOrderStatus: (id: number, orderId: number, status: OrderStatus) =>
    request<Order>(`/api/businesses/${id}/orders/${orderId}/status`, json({ status })),
  create: async (description: string, priceList: string, photo: File | null) => {
    const form = new FormData();
    form.set("description", description);
    form.set("price_list", priceList);
    if (photo) form.set("photo", photo);
    const b = await request<Business>("/api/businesses", { method: "POST", body: form });
    if (b.csrf) await session.me(true); // a new guest workspace began: pick up its token
    return b;
  },
  /** S17: read her (changed) words again for this shop, before launch. Same shape as create. */
  reread: (id: number, description: string, priceList: string, photo: File | null) => {
    const form = new FormData();
    form.set("description", description);
    form.set("price_list", priceList);
    if (photo) form.set("photo", photo);
    return request<Business>(`/api/businesses/${id}/reread`, { method: "POST", body: form });
  },
  remove: (id: number) => request<{ ok: boolean }>(`/api/businesses/${id}`, { method: "DELETE" }),
  names: (id: number) => request<NameIdea[]>(`/api/businesses/${id}/names`),
  plan: (_bid: number, id: number) => request<Plan>(`/api/plans/${id}`),
  createPlan: (businessId: number, mode: "sandbox" | "full", domain?: string, real = false) =>
    request<Plan>(`/api/businesses/${businessId}/plans`, json({ mode, domain: domain ?? null, real })),
  approve: (_bid: number, planId: number, approvedBy: string) =>
    request<{ ok: boolean }>(`/api/plans/${planId}/approve`, json({ approved_by: approvedBy || "owner" })),
  resume: (_bid: number, planId: number) => request<{ ok: boolean }>(`/api/plans/${planId}/resume`, { method: "POST" }),
  practiceBuy: (_bid: number, planId: number) =>
    request<{ ok: boolean }>(`/api/plans/${planId}/practice-buy`, { method: "POST" }),
  save: (id: number, profile: Profile, subdomain: string) =>
    request<Business>(`/api/businesses/${id}`, json({ profile, subdomain }, "PUT")),
  themes: () => request<ThemeInfo[]>("/api/themes"),
  setTheme: (id: number, theme: string, accent: string) =>
    request<Business>(`/api/businesses/${id}/theme`, json({ theme, accent }, "PUT")),
  setSignature: (id: number, motif: string, art: string) =>
    request<Business>(`/api/businesses/${id}/signature`, json({ motif, art }, "PUT")),
  contact: (name: string, email: string, message: string, website: string) =>
    request<{ ok: boolean; message: string }>("/api/contact", json({ name, email, message, website })),
  // look: the picker's small inline preview; it doesn't count as "she looked at her preview" for the go-live list.
  preview: async (id: number, page: "home" | "privacy" = "home", inline = false): Promise<string> => {
    const r = await send(`/api/businesses/${id}/preview?page=${page}${inline ? "&inline=1" : ""}`).catch(() => null);
    if (!r || !r.ok) throw new ApiError("We couldn't load the preview. Please try again.", r?.status ?? 0);
    return r.text();
  },
  report: (id: number) => request<Report>(`/api/businesses/${id}/report`),
  runChecks: (id: number) => request<{ ok: boolean; run_id: number }>(`/api/businesses/${id}/checks`, { method: "POST" }),
  photos: (id: number) => request<PhotoList>(`/api/businesses/${id}/photos`),
  addPhoto: (id: number, file: File, item = "") => {
    const form = new FormData();
    form.append("file", file);
    if (item) form.append("item", item);
    return request<PhotoList>(`/api/businesses/${id}/photos`, { method: "POST", body: form });
  },
  /** S17: a photo from the Describe list, by what she typed; the server finds the item the Reader made from it. */
  addItemPhoto: (id: number, file: File, typedName: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("item_hint", typedName);
    return request<PhotoList>(`/api/businesses/${id}/photos`, { method: "POST", body: form });
  },
  removePhoto: (id: number, photoId: number) =>
    request<PhotoList>(`/api/businesses/${id}/photos/${photoId}`, { method: "DELETE" }),
  describeProblem: (id: number, symptom: string) =>
    request<{ ok: boolean; run_id: number }>(`/api/businesses/${id}/describe-problem`, json({ symptom })),
  // ---- proof ----
  shareStatus: (id: number) => request<{ active: boolean; created_at: string | null }>(`/api/businesses/${id}/share`),
  share: (id: number) => request<{ url: string }>(`/api/businesses/${id}/share`, { method: "POST" }),
  unshare: (id: number) => request<{ ok: boolean }>(`/api/businesses/${id}/share`, { method: "DELETE" }),
  confirmTestOrder: (token: string) => request<{ ok: boolean; shop: string }>("/api/proof/confirm", json({ token })),
  watches: () => request<{ limit: number; watches: Watch[] }>("/api/watches"),
  addWatch: (address: string) => request<Watch>("/api/watches", json({ address })),
  removeWatch: (id: number) => request<{ ok: boolean; left: number }>(`/api/watches/${id}`, { method: "DELETE" }),
  checkAddress: (address: string) =>
    request<{ address: string; read_only: boolean; results: AddressResult[] }>("/api/check-address", json({ address })),
  // ---- team ----
  admin: {
    users: (status?: string) => request<AdminUser[]>(`/api/admin/users${status ? `?status=${status}` : ""}`),
    approve: (id: number) => request<AdminUser>(`/api/admin/users/${id}/approve`, { method: "POST" }),
    reject: (id: number, reason: string) => request<AdminUser>(`/api/admin/users/${id}/reject`, json({ reason })),
    suspend: (id: number, reason: string) => request<AdminUser>(`/api/admin/users/${id}/suspend`, json({ reason })),
    shops: () => request<AdminShop[]>("/api/admin/businesses"),
    pause: (id: number, reason: string) => request<{ ok: boolean }>(`/api/admin/businesses/${id}/pause`, json({ reason })),
    unpause: (id: number) => request<{ ok: boolean }>(`/api/admin/businesses/${id}/unpause`, { method: "POST" }),
    clearReview: (id: number) => request<{ ok: boolean }>(`/api/admin/businesses/${id}/clear-review`, { method: "POST" }),
    publishEdit: (id: number) => request<{ ok: boolean }>(`/api/admin/businesses/${id}/publish-edit`, { method: "POST" }),
    discardEdit: (id: number) => request<{ ok: boolean }>(`/api/admin/businesses/${id}/discard-edit`, { method: "POST" }),
    reports: () => request<ShopReportRow[]>("/api/admin/reports"),
    closeReport: (id: number, reason: string) => request<{ ok: boolean }>(`/api/admin/reports/${id}/close`, json({ reason })),
    zoneFindings: () => request<ZoneFinding[]>("/api/admin/zone-findings"),
    outbox: () => request<OutboxSummary>("/api/admin/outbox"),
    zoneCheck: () => request<{ open: ZoneFinding[] }>("/api/admin/zone-check", { method: "POST" }),
    zoneApprove: (id: number) => request<ZoneFinding>(`/api/admin/zone-findings/${id}/approve`, { method: "POST" }),
    zoneDismiss: (id: number) => request<ZoneFinding>(`/api/admin/zone-findings/${id}/dismiss`, { method: "POST" }),
  },
  setDemoFault: (id: number, fault: DemoFaultName) =>
    request<{ ok: boolean; demo_fault: string }>(`/api/admin/businesses/${id}/demo-fault`, json({ fault }, "PUT")),
};

export type OutboxSummary = {
  counts: Record<"queued" | "sending" | "sent" | "failed" | "dead", number>;
  sent_today: number;
  daily_limit: number;
  recent_errors: { id: number; kind: string; status: string; attempts: number; error: string; at: string }[];
};

export const inr = (n: number) => "₹" + new Intl.NumberFormat("en-IN").format(n);

export const usd = (n: number) => "$" + n.toFixed(2);
