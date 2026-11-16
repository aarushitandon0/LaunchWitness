import { useEffect, useState } from "react";
import { api, ApiError, inr, Order } from "./api";
import { ErrorBox } from "./Describe";

/** A shop's orders, newest first (test orders are left out by the server). */
export function OrdersPage({ businessId }: { businessId: number }) {
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    api.orders(businessId).then(setOrders).catch(setError);
  }, [businessId]);
  if (error) return <ErrorBox error={error} />;
  if (!orders) return <p>Loading…</p>;
  return (
    <>
      <h1>Orders</h1>
      {orders.length === 0 ? (
        <p className="muted">No orders yet.</p>
      ) : (
        <ul className="card orders">
          {orders.map((o) => (
            <li key={o.id}>
              <strong>{o.customer_name}</strong> — {inr(o.total_inr)}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
