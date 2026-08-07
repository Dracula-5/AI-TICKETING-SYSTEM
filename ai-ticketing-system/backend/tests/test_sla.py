"""
Tests for SLA monitoring logic: escalation, SLA window calculation, and
the background check function.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import Ticket
from app.services.sla_checker import check_and_escalate_sla


def _make_ticket(db, tenant_id, user_id, sla_offset_hours, status="open"):
    """Insert a ticket whose SLA due date is offset_hours from now."""
    ticket = Ticket(
        title="SLA test ticket",
        description="desc",
        priority="high",
        status=status,
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        sla_due=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=sla_offset_hours),
        is_escalated=False,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


class TestSLAWindows:
    def _parse_due(self, sla_due_str: str) -> datetime:
        """Parse ISO datetime string from the API, strip timezone info."""
        return datetime.fromisoformat(sla_due_str).replace(tzinfo=None)

    def test_critical_ticket_gets_2h_sla(self, client, customer_user, tenant):
        from tests.conftest import auth_headers
        resp = client.post("/tickets/", json={
            "title": "EMERGENCY server down",
            "description": "complete power outage in ICU",
            "tenant_id": tenant.id,
        }, headers=auth_headers(customer_user))
        assert resp.status_code == 201
        data = resp.json()
        assert data["priority"] == "critical"
        due = self._parse_due(data["sla_due"])
        window = due - datetime.now(timezone.utc).replace(tzinfo=None)
        # Should be ~2 hours (allow 30-second execution slack)
        assert timedelta(hours=1, minutes=58) <= window <= timedelta(hours=2, minutes=1)

    def test_low_priority_gets_24h_sla(self, client, customer_user, tenant):
        from tests.conftest import auth_headers
        resp = client.post("/tickets/", json={
            "title": "Minor cosmetic issue",
            "description": "Button label slightly off",
            "tenant_id": tenant.id,
        }, headers=auth_headers(customer_user))
        assert resp.status_code == 201
        data = resp.json()
        assert data["priority"] == "low"
        due = self._parse_due(data["sla_due"])
        window = due - datetime.now(timezone.utc).replace(tzinfo=None)
        assert timedelta(hours=23, minutes=58) <= window <= timedelta(hours=24, minutes=1)


class TestEscalation:
    def test_overdue_open_ticket_gets_escalated(self, db, tenant, customer_user):
        ticket = _make_ticket(db, tenant.id, customer_user.id, sla_offset_hours=-1)
        assert not ticket.is_escalated
        count = check_and_escalate_sla(db)
        db.refresh(ticket)
        assert ticket.is_escalated
        assert count >= 1

    def test_future_ticket_not_escalated(self, db, tenant, customer_user):
        ticket = _make_ticket(db, tenant.id, customer_user.id, sla_offset_hours=+6)
        check_and_escalate_sla(db)
        db.refresh(ticket)
        assert not ticket.is_escalated

    def test_closed_ticket_not_re_escalated(self, db, tenant, customer_user):
        ticket = _make_ticket(db, tenant.id, customer_user.id,
                              sla_offset_hours=-1, status="closed")
        count = check_and_escalate_sla(db)
        db.refresh(ticket)
        # Closed tickets must never be touched by the escalation job
        assert not ticket.is_escalated

    def test_already_escalated_ticket_not_counted_twice(self, db, tenant, customer_user):
        ticket = _make_ticket(db, tenant.id, customer_user.id, sla_offset_hours=-1)
        check_and_escalate_sla(db)  # first pass escalates
        count2 = check_and_escalate_sla(db)  # second pass should skip it
        assert count2 == 0
