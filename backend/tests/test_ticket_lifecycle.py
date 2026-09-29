from datetime import timedelta

from app.db.database import utcnow
from app.db.models import AuditLog, Notification, Ticket, TicketStatusHistory
from tests.conftest import assign, auth, create_ticket, move, team_id

API = "/api/v1/tickets"


def history(db, ticket_id):
    return [
        (h.from_status, h.to_status, h.actor_type)
        for h in db.query(TicketStatusHistory)
        .filter(TicketStatusHistory.ticket_id == ticket_id)
        .order_by(TicketStatusHistory.id)
    ]


class TestCreationAndTriage:
    def test_created_ticket_is_triaged_and_routed_by_rules(self, client, db, org_a, customer_a):
        t = create_ticket(
            client, customer_a, title="VPN not connecting", description="VPN client error 809 since morning"
        )
        assert t["status"] == "triaged"
        assert t["number"] == 1
        assert t["category"] == "Network & Connectivity"
        assert t["team"]["name"] == "Infrastructure"
        assert t["triage_source"] == "rules"
        assert t["requester"]["id"] == customer_a.id
        assert history(db, t["id"]) == [(None, "submitted", "user"), ("submitted", "triaged", "system")]
        reason = db.query(TicketStatusHistory.reason).filter(TicketStatusHistory.to_status == "triaged").scalar()
        assert "'vpn'" in reason and "Infrastructure" in reason

    def test_sla_due_dates_follow_org_policy(self, client, customer_a):
        t = create_ticket(
            client, customer_a, title="Payroll portal down", description="Outage for all users", priority="critical"
        )
        assert t["priority"] == "critical"
        created = t["created_at"]
        assert t["sla"]["first_response_due"] > created and t["sla"]["resolution_due"] > t["sla"]["first_response_due"]
        assert t["sla"]["state"] == "ok"

    def test_numbers_are_sequential_per_org(self, client, customer_a, customer_b):
        assert create_ticket(client, customer_a)["number"] == 1
        assert create_ticket(client, customer_a)["number"] == 2
        assert create_ticket(client, customer_b)["number"] == 1

    def test_unknown_category_rejected(self, client, customer_a):
        resp = client.post(
            API, json={"title": "Hello", "description": "x", "category": "Nope"}, headers=auth(customer_a)
        )
        assert resp.status_code == 422

    def test_analyst_cannot_create(self, client, analyst_a):
        resp = client.post(API, json={"title": "Hello", "description": "x"}, headers=auth(analyst_a))
        assert resp.status_code == 403

    def test_auto_assign_to_least_loaded_team_member(self, client, db, org_a, agent_a, agent_a2, customer_a):
        org_a.settings = {**org_a.settings, "auto_assign": True}
        db.commit()
        # Both agents are in Service Desk; the first ticket goes to the lower id,
        # the next to whoever then has fewer open tickets.
        first = create_ticket(client, customer_a, title="Laptop screen flickers", description="hardware issue")
        second = create_ticket(client, customer_a, title="Printer jammed", description="printer on floor 2")
        assert first["status"] == second["status"] == "assigned"
        assert {first["assignee"]["id"], second["assignee"]["id"]} == {agent_a.id, agent_a2.id}


class TestHappyPath:
    def test_full_lifecycle_with_customer_confirmation(self, client, db, manager_a, agent_a, customer_a):
        t = create_ticket(client, customer_a)
        tid = t["id"]

        r = assign(client, manager_a, tid, agent_a.id)
        assert r.status_code == 200 and r.json()["status"] == "assigned"
        assert (
            db.query(Notification)
            .filter(Notification.user_id == agent_a.id, Notification.type == "ticket_assigned")
            .count()
            == 1
        )

        r = move(client, agent_a, tid, "acknowledged")
        assert r.status_code == 200
        assert r.json()["sla"]["first_responded_at"] is not None

        assert move(client, agent_a, tid, "in_progress").json()["status"] == "in_progress"
        assert move(client, agent_a, tid, "waiting_for_customer", reason="Which VPN client version?").status_code == 200
        ticket = db.get(Ticket, tid)
        assert ticket.sla_paused_at is not None

        # The requester's reply resumes work automatically.
        r = client.post(f"{API}/{tid}/comments", json={"content": "Version 5.2"}, headers=auth(customer_a))
        assert r.status_code == 201
        db.expire_all()
        assert db.get(Ticket, tid).status == "in_progress"
        assert db.get(Ticket, tid).sla_paused_at is None

        assert move(client, agent_a, tid, "resolved").status_code == 422  # summary required
        r = move(client, agent_a, tid, "resolved", resolution_summary="Upgraded the VPN client to 5.3")
        assert r.status_code == 200 and r.json()["resolved_at"]
        assert (
            db.query(Notification)
            .filter(Notification.user_id == customer_a.id, Notification.type == "ticket_resolved")
            .count()
            == 1
        )

        r = client.post(f"{API}/{tid}/confirm-resolution", json={"accepted": True}, headers=auth(customer_a))
        assert r.status_code == 200 and r.json()["status"] == "closed"

        assert [h[1] for h in history(db, tid)] == [
            "submitted",
            "triaged",
            "assigned",
            "acknowledged",
            "in_progress",
            "waiting_for_customer",
            "in_progress",
            "resolved",
            "closed",
        ]
        actions = {a for (a,) in db.query(AuditLog.action).filter(AuditLog.entity_id == str(tid))}
        assert {"ticket.create", "ticket.assign", "ticket.transition"} <= actions

    def test_customer_rejects_resolution(self, client, db, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, tid, agent_a.id)
        move(client, agent_a, tid, "in_progress")
        move(client, agent_a, tid, "resolved", resolution_summary="Restarted")
        resp = client.post(f"{API}/{tid}/confirm-resolution", json={"accepted": False}, headers=auth(customer_a))
        assert resp.status_code == 422  # reason required
        resp = client.post(
            f"{API}/{tid}/confirm-resolution",
            json={"accepted": False, "reason": "Still broken"},
            headers=auth(customer_a),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "reopened" and body["reopened_count"] == 1 and body["resolved_at"] is None
        assert (
            db.query(Notification)
            .filter(Notification.user_id == agent_a.id, Notification.type == "ticket_reopened")
            .count()
            == 1
        )
        assert move(client, agent_a, tid, "in_progress").status_code == 200


class TestTransitionRules:
    def test_cannot_skip_to_in_progress_without_assignee(self, client, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        r = move(client, agent_a, tid, "in_progress")
        assert r.status_code == 409

    def test_illegal_transition_is_rejected(self, client, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assert move(client, manager_a, tid, "acknowledged").status_code == 409  # not assigned yet
        assert move(client, manager_a, tid, "assigned").status_code == 400  # only via /assign
        assert move(client, manager_a, tid, "bogus").status_code == 422

    def test_only_assignee_or_manager_can_work(self, client, manager_a, agent_a, agent_a2, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, tid, agent_a.id)
        assert move(client, agent_a2, tid, "acknowledged").status_code == 403
        assert move(client, customer_a, tid, "acknowledged").status_code == 403
        assert move(client, manager_a, tid, "acknowledged").status_code == 200

    def test_escalation_needs_reason_and_notifies_leads(self, client, db, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, tid, agent_a.id)
        assert move(client, agent_a, tid, "escalated").status_code == 422
        assert move(client, agent_a, tid, "escalated", reason="Needs network team").status_code == 200
        assert (
            db.query(Notification)
            .filter(Notification.user_id == manager_a.id, Notification.type == "ticket_escalated")
            .count()
            == 1
        )

    def test_requester_can_withdraw_before_work_but_not_during(self, client, manager_a, agent_a, customer_a):
        withdrawn = create_ticket(client, customer_a)["id"]
        assert move(client, customer_a, withdrawn, "closed", reason="Fixed itself").status_code == 200

        busy = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, busy, agent_a.id)
        move(client, agent_a, busy, "in_progress")
        assert move(client, customer_a, busy, "closed", reason="nvm").status_code == 403

    def test_manager_can_close_any_open_ticket_with_reason(self, client, manager_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assert move(client, manager_a, tid, "closed").status_code == 422
        assert move(client, manager_a, tid, "closed", reason="Duplicate of #1").status_code == 200

    def test_reopen_window(self, client, db, manager_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        move(client, manager_a, tid, "closed", reason="Duplicate")
        db.query(Ticket).filter(Ticket.id == tid).update({Ticket.closed_at: utcnow() - timedelta(days=30)})
        db.commit()
        r = move(client, customer_a, tid, "reopened", reason="Came back")
        assert r.status_code == 409

    def test_customer_cannot_comment_on_closed_ticket(self, client, manager_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        move(client, manager_a, tid, "closed", reason="Duplicate")
        r = client.post(f"{API}/{tid}/comments", json={"content": "hello?"}, headers=auth(customer_a))
        assert r.status_code == 409

    def test_allowed_transitions_reflect_the_viewer(self, client, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, tid, agent_a.id)
        as_agent = client.get(f"{API}/{tid}", headers=auth(agent_a)).json()["allowed_transitions"]
        as_customer = client.get(f"{API}/{tid}", headers=auth(customer_a)).json()["allowed_transitions"]
        assert "acknowledged" in as_agent and "resolved" in as_agent
        assert as_customer == ["closed"]


class TestAssignment:
    def test_agent_can_take_unassigned_ticket(self, client, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        r = assign(client, agent_a, tid, agent_a.id)
        assert r.status_code == 200 and r.json()["assignee"]["id"] == agent_a.id

    def test_agent_cannot_assign_others_or_steal(self, client, manager_a, agent_a, agent_a2, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assert assign(client, agent_a, tid, agent_a2.id).status_code == 403
        assign(client, manager_a, tid, agent_a2.id)
        assert assign(client, agent_a, tid, agent_a.id).status_code == 403

    def test_cannot_assign_to_customer_or_foreign_user(self, client, manager_a, customer_a, agent_b):
        tid = create_ticket(client, customer_a)["id"]
        assert assign(client, manager_a, tid, customer_a.id).status_code == 422
        assert assign(client, manager_a, tid, agent_b.id).status_code == 404

    def test_unassigning_returns_ticket_to_triaged(self, client, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, tid, agent_a.id)
        r = assign(client, agent_a, tid, None)
        assert r.status_code == 200 and r.json()["status"] == "triaged" and r.json()["assignee"] is None

    def test_team_reassignment(self, client, db, org_a, manager_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        security = team_id(db, org_a, "Security")
        r = client.post(f"{API}/{tid}/assign", json={"assignee_id": None, "team_id": security}, headers=auth(manager_a))
        assert r.status_code == 200 and r.json()["team"]["name"] == "Security"


class TestEditing:
    def test_staff_change_priority_recomputes_sla_and_marks_manual(self, client, agent_a, customer_a):
        t = create_ticket(client, customer_a, title="Question about leave", description="How many days do I have?")
        r = client.patch(f"{API}/{t['id']}", json={"priority": "critical"}, headers=auth(agent_a))
        assert r.status_code == 200
        body = r.json()
        assert body["priority"] == "critical" and body["triage_source"] == "manual"
        assert body["sla"]["resolution_due"] < t["sla"]["resolution_due"]

    def test_customer_may_edit_text_only_before_work(self, client, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assert client.patch(f"{API}/{tid}", json={"title": "Better title"}, headers=auth(customer_a)).status_code == 200
        assert client.patch(f"{API}/{tid}", json={"priority": "critical"}, headers=auth(customer_a)).status_code == 403
        assign(client, manager_a, tid, agent_a.id)
        assert (
            client.patch(f"{API}/{tid}", json={"title": "Changed again"}, headers=auth(customer_a)).status_code == 403
        )

    def test_edit_is_audited_with_diff(self, client, db, agent_a, customer_a):
        tid = create_ticket(client, customer_a, title="Something odd", description="hmm")["id"]
        client.patch(f"{API}/{tid}", json={"category": "Security"}, headers=auth(agent_a))
        entry = db.query(AuditLog).filter(AuditLog.action == "ticket.update").one()
        assert entry.changes["category"][1] == "Security" and entry.actor_user_id == agent_a.id


class TestListing:
    def test_filters_and_pagination(self, client, manager_a, agent_a, customer_a):
        for i in range(7):
            create_ticket(client, customer_a, title=f"Ticket number {i}", description="desc")
        first = client.get(API, params={"page_size": 5}, headers=auth(agent_a)).json()
        assert first["total"] == 7 and len(first["items"]) == 5
        second = client.get(API, params={"page_size": 5, "page": 2}, headers=auth(agent_a)).json()
        assert len(second["items"]) == 2

        tid = first["items"][0]["id"]
        assign(client, manager_a, tid, agent_a.id)
        mine = client.get(API, params={"assignee": "me"}, headers=auth(agent_a)).json()
        assert [t["id"] for t in mine["items"]] == [tid]
        assert client.get(API, params={"assignee": "unassigned"}, headers=auth(agent_a)).json()["total"] == 6
        assert client.get(API, params={"q": "number 3"}, headers=auth(agent_a)).json()["total"] == 1
        assert client.get(API, params={"q": "#2"}, headers=auth(agent_a)).json()["total"] >= 1
        assert client.get(API, params={"status": "done"}, headers=auth(agent_a)).json()["total"] == 0

    def test_priority_sort_puts_most_urgent_first(self, client, customer_a, agent_a):
        create_ticket(client, customer_a, title="low one", description="x", priority="low")
        create_ticket(client, customer_a, title="crit one", description="x", priority="critical")
        items = client.get(API, params={"sort": "-priority"}, headers=auth(agent_a)).json()["items"]
        assert items[0]["priority"] == "critical"
