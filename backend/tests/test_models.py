from sqlmodel import select

from app import audit
from app.models import AuditEvent, Business


def test_create_business_and_audit(session):
    b = Business(name="Meera's Home Cakes", domain="meerascakes.in", subdomain="meera")
    session.add(b)
    session.commit()
    session.refresh(b)
    audit.record(session, actor="system", action="create_business", result="ok", business_id=b.id)
    events = session.exec(select(AuditEvent)).all()
    assert [e.action for e in events] == ["create_business"]
