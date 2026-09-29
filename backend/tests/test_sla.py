from datetime import timedelta

from app.db.database import utcnow
from app.db.models import AuditLog, Notification, Ticket
from app.services.sla import run_sla_sweep
from tests.conftest import assign, auth, create_ticket, move

API = "/api/v1/tickets"


def age(db, ticket_id, **delta):
    """Shift a ticket's clock into the past."""
    t = db.get(Ticket, ticket_id)
    shift = timedelta(**delta)
    t.created_at -= shift
    t.first_response_due -= shift
    t.resolution_due -= shift
    db.commit()


class TestSweep:
    def test_first_response_breach_is_recorded_once_and_notified(self, client, db, manager_a, customer_a):
        tid = create_ticket(client, customer_a, priority="high")["id"]
        age(db, tid, minutes=61)  # high: 60 min first response
        result = run_sla_sweep(db)
        assert result["first_response_breaches"] == 1 and result["resolution_breaches"] == 0
        assert db.get(Ticket, tid).first_response_breached_at is not None
        assert (
            db.query(Notification)
            .filter(Notification.user_id == manager_a.id, Notification.type == "sla_breach")
            .count()
            == 1
        )
        # idempotent
        assert run_sla_sweep(db)["first_response_breaches"] == 0

    def test_acknowledged_ticket_has_no_first_response_breach(self, client, db, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a, priority="high")["id"]
        assign(client, manager_a, tid, agent_a.id)
        move(client, agent_a, tid, "acknowledged")
        age(db, tid, minutes=61)
        assert run_sla_sweep(db)["first_response_breaches"] == 0

    def test_resolution_breach_escalates(self, client, db, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a, priority="critical")["id"]
        assign(client, manager_a, tid, agent_a.id)
        move(client, agent_a, tid, "in_progress")
        age(db, tid, hours=5)  # critical: 4h resolution
        result = run_sla_sweep(db)
        assert result["resolution_breaches"] == 1 and result["escalated"] == 1
        db.expire_all()
        t = db.get(Ticket, tid)
        assert t.status == "escalated" and t.resolution_breached_at is not None
        assert db.query(AuditLog).filter(AuditLog.action == "sla.resolution_breached").count() == 1
        assert run_sla_sweep(db)["escalated"] == 0

    def test_paused_ticket_is_not_breached_and_clock_shifts(self, client, db, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a, priority="critical")["id"]
        assign(client, manager_a, tid, agent_a.id)
        assert move(client, agent_a, tid, "waiting_for_customer", reason="Need logs").status_code == 200
        age(db, tid, hours=5)
        # Pretend the pause started 3 hours ago.
        t = db.get(Ticket, tid)
        t.sla_paused_at = utcnow() - timedelta(hours=3)
        db.commit()
        assert run_sla_sweep(db)["resolution_breaches"] == 0

        due_before = db.get(Ticket, tid).resolution_due
        client.post(f"{API}/{tid}/comments", json={"content": "Here are the logs"}, headers=auth(customer_a))
        db.expire_all()
        t = db.get(Ticket, tid)
        assert t.status == "in_progress" and t.sla_paused_at is None
        shifted = t.resolution_due - due_before
        assert timedelta(hours=2, minutes=59) < shifted < timedelta(hours=3, minutes=1)

    def test_auto_close_after_configured_days(self, client, db, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, tid, agent_a.id)
        move(client, agent_a, tid, "in_progress")
        move(client, agent_a, tid, "resolved", resolution_summary="Done")
        assert run_sla_sweep(db)["auto_closed"] == 0
        db.query(Ticket).filter(Ticket.id == tid).update({Ticket.resolved_at: utcnow() - timedelta(days=4)})
        db.commit()
        assert run_sla_sweep(db)["auto_closed"] == 1
        db.expire_all()
        assert db.get(Ticket, tid).status == "closed"

    def test_resolved_tickets_are_not_breached(self, client, db, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a, priority="critical")["id"]
        assign(client, manager_a, tid, agent_a.id)
        move(client, agent_a, tid, "resolved", resolution_summary="Quick fix")
        age(db, tid, hours=10)
        result = run_sla_sweep(db)
        assert result["resolution_breaches"] == result["first_response_breaches"] == 0


class TestSlaViews:
    def test_at_risk_and_breached_filters(self, client, db, agent_a, customer_a):
        safe = create_ticket(client, customer_a, priority="low")["id"]
        risky = create_ticket(client, customer_a, priority="high")["id"]
        late = create_ticket(client, customer_a, priority="high")["id"]
        for tid in (risky, late):  # responded in time, so only the resolution clock matters
            client.post(f"{API}/{tid}/comments", json={"content": "On it"}, headers=auth(agent_a))
        age(db, risky, hours=7)  # high: 8h window -> last 25% starts at 6h
        age(db, late, hours=9)
        run_sla_sweep(db)
        at_risk = client.get(API, params={"sla": "at_risk"}, headers=auth(agent_a)).json()["items"]
        breached = client.get(API, params={"sla": "breached"}, headers=auth(agent_a)).json()["items"]
        assert [t["id"] for t in at_risk] == [risky]
        assert [t["id"] for t in breached] == [late]
        states = {t["id"]: t["sla"]["state"] for t in client.get(API, headers=auth(agent_a)).json()["items"]}
        assert states[safe] == "ok" and states[risky] == "at_risk" and states[late] == "breached"

    def test_lowering_priority_does_not_erase_a_breach(self, client, db, agent_a, customer_a):
        tid = create_ticket(client, customer_a, priority="critical")["id"]
        age(db, tid, minutes=20)
        run_sla_sweep(db)
        r = client.patch(f"{API}/{tid}", json={"priority": "low"}, headers=auth(agent_a))
        assert r.json()["sla"]["first_response_breached"] is True

    def test_policy_changes_apply_to_new_tickets(self, client, db, admin_a, customer_a):
        before = create_ticket(client, customer_a, priority="low")
        r = client.put(
            "/api/v1/sla-policies",
            json={"policies": [{"priority": "low", "first_response_minutes": 30, "resolution_minutes": 120}]},
            headers=auth(admin_a),
        )
        assert r.status_code == 200
        after = create_ticket(client, customer_a, priority="low")
        assert after["sla"]["resolution_due"] < before["sla"]["resolution_due"]
        assert db.query(AuditLog).filter(AuditLog.action == "sla_policy.update").count() == 1

    def test_invalid_policy_rejected(self, client, admin_a):
        r = client.put(
            "/api/v1/sla-policies",
            json={"policies": [{"priority": "low", "first_response_minutes": 300, "resolution_minutes": 120}]},
            headers=auth(admin_a),
        )
        assert r.status_code == 422
