import pytest
from sqlmodel import select

from app.models import Approval, AuditEvent, Business
from app.safety.spend_guard import PurchaseBlocked, authorize_purchase, mark_used

DOMAIN = "meerascakes.in"


@pytest.fixture
def business(session) -> Business:
    b = Business(name="Meera's Home Cakes")
    session.add(b)
    session.commit()
    session.refresh(b)
    return b


def approve(session, business, amount=9.99, action="buy_domain", target=DOMAIN) -> Approval:
    a = Approval(business_id=business.id, action=action, target=target, amount_usd=amount, approved_by="owner")
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def attempt(session, settings, business, cost=9.99, action="buy_domain", target=DOMAIN):
    return authorize_purchase(session, settings, business_id=business.id, action=action,
                              target=target, cost_usd=cost)


def audit_results(session) -> list[str]:
    return [e.result for e in session.exec(select(AuditEvent)).all()]


def test_blocked_by_default_even_with_approval(session, settings, business):
    approve(session, business)
    with pytest.raises(PurchaseBlocked, match="ALLOW_PURCHASE"):
        attempt(session, settings, business)
    assert audit_results(session) == ["blocked"]


def test_blocked_over_cap(session, make_settings, business):
    s = make_settings(allow_purchase=True, max_spend_usd=15)
    approve(session, business, amount=100)
    with pytest.raises(PurchaseBlocked, match="cap"):
        attempt(session, s, business, cost=15.01)


def test_blocked_without_approval(session, make_settings, business):
    with pytest.raises(PurchaseBlocked, match="no owner approval"):
        attempt(session, make_settings(allow_purchase=True), business)


def test_blocked_when_approval_is_for_something_else(session, make_settings, business):
    s = make_settings(allow_purchase=True)
    approve(session, business, target="otherdomain.in")
    approve(session, business, action="buy_mailbox")
    with pytest.raises(PurchaseBlocked, match="no owner approval"):
        attempt(session, s, business)


def test_blocked_when_cost_exceeds_approved_amount(session, make_settings, business):
    s = make_settings(allow_purchase=True)
    approve(session, business, amount=8.00)
    with pytest.raises(PurchaseBlocked, match="more than the owner approved"):
        attempt(session, s, business, cost=9.99)


def test_blocked_non_positive_cost(session, make_settings, business):
    s = make_settings(allow_purchase=True)
    approve(session, business)
    with pytest.raises(PurchaseBlocked):
        attempt(session, s, business, cost=0)


def test_allowed_only_when_all_three_hold(session, make_settings, business):
    s = make_settings(allow_purchase=True, max_spend_usd=15)
    a = approve(session, business)
    assert attempt(session, s, business).id == a.id
    assert audit_results(session) == ["ok"]


def test_used_approval_cannot_be_reused(session, make_settings, business):
    s = make_settings(allow_purchase=True)
    mark_used(session, approve(session, business))
    with pytest.raises(PurchaseBlocked, match="no owner approval"):
        attempt(session, s, business)
