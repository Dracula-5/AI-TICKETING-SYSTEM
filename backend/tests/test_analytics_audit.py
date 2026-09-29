from datetime import timedelta

from app.db.database import utcnow
from app.db.models import Ticket
from app.services.sla import run_sla_sweep
from tests.conftest import assign, auth, create_ticket, make_org, make_user, move

API = "/api/v1"


class TestOverview:
    def test_empty_org(self, client, admin_a):
        body = client.get(f"{API}/analytics/overview", headers=auth(admin_a)).json()
        assert body["open_tickets"] == 0 and body["resolved_last_30d"] == 0
        assert body["avg_resolution_hours_30d"] is None and body["sla_compliance_pct_30d"] is None
        assert len(body["trend_14d"]) == 14
        assert body["data_origin"] == "real"

    def test_numbers_match_a_known_scenario(self, client, db, manager_a, agent_a, customer_a):
        # 3 tickets: one resolved after 2h with a 30-min first response, one
        # breached and escalated, one untouched.
        done = create_ticket(client, customer_a, title="Laptop battery", description="drains fast", priority="medium")[
            "id"
        ]
        late = create_ticket(client, customer_a, title="Server down", description="outage", priority="critical")["id"]
        create_ticket(client, customer_a, title="Question", description="leave balance", priority="low")

        assign(client, manager_a, done, agent_a.id)
        move(client, agent_a, done, "in_progress")
        move(client, agent_a, done, "resolved", resolution_summary="Replaced battery")
        t = db.get(Ticket, done)
        t.created_at = t.resolved_at - timedelta(hours=2)
        t.first_responded_at = t.created_at + timedelta(minutes=30)
        t.first_response_due = t.created_at + timedelta(hours=4)
        t.resolution_due = t.created_at + timedelta(hours=24)
        lt = db.get(Ticket, late)
        lt.first_response_due -= timedelta(hours=5)
        lt.resolution_due -= timedelta(hours=5)
        db.commit()
        run_sla_sweep(db)

        body = client.get(f"{API}/analytics/overview", headers=auth(manager_a)).json()
        assert body["open_tickets"] == 2
        assert body["created_today"] >= 2
        assert body["unassigned_open"] == 2
        assert body["sla_breached_open"] == 1
        assert body["resolved_last_30d"] == 1
        assert body["avg_resolution_hours_30d"] == 2.0
        assert body["avg_first_response_minutes_30d"] == 30.0
        assert body["sla_compliance_pct_30d"] == 100.0
        statuses = {i["key"]: i["count"] for i in body["by_status"]}
        assert statuses == {"resolved": 1, "escalated": 1, "triaged": 1}
        assert sum(p["created"] for p in body["trend_14d"]) == 3
        assert sum(p["resolved"] for p in body["trend_14d"]) == 1

    def test_demo_org_is_labelled(self, client, db):
        demo = make_org(db, "Demo Org", is_demo=True, data_origin="demo")
        admin = make_user(db, demo, "org_admin", "admin@demo.example.com")
        assert client.get(f"{API}/analytics/overview", headers=auth(admin)).json()["data_origin"] == "demo"


class TestAuditLog:
    def test_actions_are_recorded_with_request_context(self, client, db, admin_a, customer_a):
        create_ticket(client, customer_a)
        client.post(
            f"{API}/organizations/me/invitations",
            json={"email": "n@acme.example.com", "role": "agent"},
            headers={**auth(admin_a), "X-Request-ID": "req-12345678"},
        )
        page = client.get(f"{API}/audit-logs", headers=auth(admin_a)).json()
        actions = [i["action"] for i in page["items"]]
        assert "user.invite" in actions and "ticket.create" in actions
        invite = next(i for i in page["items"] if i["action"] == "user.invite")
        assert invite["request_id"] == "req-12345678" and invite["actor_email"] == admin_a.email

    def test_filters(self, client, admin_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        only_tickets = client.get(f"{API}/audit-logs", params={"action": "ticket."}, headers=auth(admin_a)).json()
        assert only_tickets["total"] >= 2 and all(i["action"].startswith("ticket.") for i in only_tickets["items"])
        entity = client.get(
            f"{API}/audit-logs", params={"entity_type": "ticket", "entity_id": str(tid)}, headers=auth(admin_a)
        ).json()
        assert entity["total"] >= 1
        future = client.get(
            f"{API}/audit-logs", params={"since": (utcnow() + timedelta(days=1)).isoformat()}, headers=auth(admin_a)
        ).json()
        assert future["total"] == 0


class TestPlatformOverview:
    def test_counts_split_by_origin(self, client, db, platform_admin, customer_a):
        demo = make_org(db, "Demo Org", is_demo=True, data_origin="demo")
        make_user(db, demo, "customer", "c@demo.example.com", data_origin="demo")
        create_ticket(client, customer_a)
        body = client.get(f"{API}/platform/overview", headers=auth(platform_admin)).json()
        assert body["organizations"] == 2 and body["demo_organizations"] == 1
        assert body["users_by_origin"]["demo"] == 1
        assert body["tickets_by_origin"] == {"real": 1}
