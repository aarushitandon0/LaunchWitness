import { useEffect, useState } from "react";
import { api, ApiError, Business, inr, Order, OrderStatus } from "./api";
import { ErrorBox } from "./Describe";

const LABEL: Record<OrderStatus, string> = {
  new: "New",
  confirmed: "Confirmed",
  paid: "Paid",
  done: "Done",
  cancelled: "Cancelled",
};
const ACTION: Record<OrderStatus, string> = {
  new: "",
  confirmed: "Mark confirmed",
  paid: "Mark paid",
  done: "Mark done",
  cancelled: "Cancel order",
};

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });

/** A shop's orders, newest first, for its owner (test orders are left out by the server). Mobile-first. */
export function OrdersPage({ businessId }: { businessId: number }) {
  const [biz, setBiz] = useState<Business | null>(null);
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [rowError, setRowError] = useState<{ id: number; message: string } | null>(null);

  useEffect(() => {
    api.get(businessId).then(setBiz).catch(setError);
    api.orders(businessId).then(setOrders).catch(setError);
  }, [businessId]);

  const move = async (o: Order, to: OrderStatus) => {
    if (to === "cancelled" && !window.confirm(`Cancel order ${o.ref}? This can't be undone.`)) return;
    setBusy(o.id);
    setRowError(null);
    try {
      const updated = await api.setOrderStatus(businessId, o.id, to);
      setOrders((list) => (list ?? []).map((x) => (x.id === o.id ? updated : x)));
    } catch (e) {
      setRowError({ id: o.id, message: e instanceof ApiError ? e.message : "That didn't work. Please try again." });
    } finally {
      setBusy(null);
    }
  };

  if (error) return <ErrorBox error={error} />;
  if (!orders || !biz) return <p>Loading…</p>;
  const fresh = orders.filter((o) => o.status === "new").length;
  return (
    <>
      <p className="eyebrow">
        <a href="#/shops">My shops</a> · {biz.name}
      </p>
      <h1>Orders</h1>
      <p className="tagline">
        {orders.length === 0
          ? "No orders yet. When a customer orders on your shop, it appears here and in your email."
          : `${orders.length} order${orders.length === 1 ? "" : "s"}${fresh ? `, ${fresh} new` : ""}. Newest first.`}
      </p>
      <p className="muted small">
        “Message on WhatsApp” opens your own WhatsApp with a message ready to send to the customer. We never send
        anything for you, and customers don't see these statuses.
      </p>
      <ul className="order-list">
        {orders.map((o) => (
          <li key={o.id} className={`order-card order-${o.status}`}>
            <div className="order-top">
              <strong>{o.customer_name}</strong>
              <span className={`order-status s-${o.status}`}>{LABEL[o.status]}</span>
            </div>
            <div className="muted small">
              {o.ref} · {when(o.created_at)}
            </div>
            <ul className="order-items">
              {o.items.length ? (
                o.items.map((it, i) => (
                  <li key={i}>
                    <span>
                      {it.qty} × {it.name}
                    </span>
                    <span>{inr(it.qty * it.price_inr)}</span>
                  </li>
                ))
              ) : (
                <li>
                  <span>No items chosen, see the note</span>
                </li>
              )}
              <li className="order-total">
                <span>Total</span>
                <span>{inr(o.total_inr)}</span>
              </li>
            </ul>
            {o.note && <p className="order-note">“{o.note}”</p>}
            <p className="order-phone">{o.tel_url ? <a href={o.tel_url}>{o.customer_phone}</a> : o.customer_phone}</p>
            {o.email_status === "failed" && <p className="warn">We couldn't email this order to you.</p>}
            <div className="order-actions">
              {o.whatsapp_url && (
                <a className="btn btn-wa btn-sm" href={o.whatsapp_url} target="_blank" rel="noopener noreferrer">
                  Message on WhatsApp
                </a>
              )}
              {o.next_statuses.map((to) => (
                <button
                  key={to}
                  type="button"
                  className={to === "cancelled" ? "btn btn-ghost btn-sm" : "btn btn-primary btn-sm"}
                  disabled={busy === o.id}
                  onClick={() => move(o, to)}
                >
                  {ACTION[to]}
                </button>
              ))}
            </div>
            {rowError?.id === o.id && (
              <p className="error" role="alert">
                {rowError.message}
              </p>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
