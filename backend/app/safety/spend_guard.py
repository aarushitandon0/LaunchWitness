"""The only gate in front of anything that spends money.

A purchase is allowed only when ALL of these hold:
  1. ALLOW_PURCHASE=true
  2. 0 < cost <= MAX_SPEND_USD
  3. an unused owner Approval exists for this business + action + target,
     and the approved amount covers the cost.

Every decision (allowed or blocked) is written to the audit log.
"""

from sqlmodel import Session, select

from app import audit
from app.config import Settings
from app.models import Approval, utcnow


class PurchaseBlocked(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def authorize_purchase(
    session: Session,
    settings: Settings,
    *,
    business_id: int,
    action: str,
    target: str,
    cost_usd: float,
    actor: str = "system",
) -> Approval:
    """Return the matching Approval, or raise PurchaseBlocked."""
    what = f"{action} {target} ${cost_usd:.2f}"

    def block(reason: str) -> PurchaseBlocked:
        audit.record(session, actor=actor, action=f"authorize_{action}", target=target,
                     result="blocked", detail=f"{what}: {reason}", business_id=business_id)
        return PurchaseBlocked(reason)

    if not settings.allow_purchase:
        raise block("purchases are disabled (ALLOW_PURCHASE=false)")
    if cost_usd <= 0:
        raise block("cost must be positive")
    if cost_usd > settings.max_spend_usd:
        raise block(f"cost is over the cap (MAX_SPEND_USD={settings.max_spend_usd:.2f})")

    approval = session.exec(
        select(Approval).where(
            Approval.business_id == business_id,
            Approval.action == action,
            Approval.target == target,
            Approval.used_at.is_(None),  # type: ignore[union-attr]
        )
    ).first()
    if approval is None:
        raise block("no owner approval for this purchase")
    if cost_usd > approval.amount_usd:
        raise block(f"cost is more than the owner approved (${approval.amount_usd:.2f})")

    audit.record(session, actor=actor, action=f"authorize_{action}", target=target,
                 result="ok", detail=f"{what}: approval #{approval.id}", business_id=business_id)
    return approval


def mark_used(session: Session, approval: Approval) -> None:
    """Call after a successful purchase so the approval can't be reused."""
    approval.used_at = utcnow()
    session.add(approval)
    session.commit()
