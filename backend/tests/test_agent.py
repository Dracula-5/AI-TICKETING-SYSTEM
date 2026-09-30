"""Triage agent (P7) and approval queue (P8): validation, no-change, policy,
verification with rollback, high-risk actions waiting for a person, and the
queue/bulk decisions a human uses to work through them."""

import io
from datetime import timedelta

from app.agent import tools
from app.db.models import AgentRun, AIPrediction, Category, Ticket, TicketComment
from app.services.jobs import run_due_jobs
from tests.conftest import assign, auth, create_ticket
from tests.test_ai import VPN_QUERY, history, mislabel, predictions

API = "/api/v1"


def train(db, org, customer, agent, n_each=6):
    org.settings = {**org.settings, "ai_min_history": 3}
    history(db, org, customer, agent, n_each=n_each)


class TestAgentRun:
    def test_run_is_logged_with_step_outcomes(self, client, db, org_a, agent_a, customer_a):
        train(db, org_a, customer_a, agent_a)
        t = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1])
        run_due_jobs()
        run = db.query(AgentRun).filter(AgentRun.ticket_id == t["id"]).one()
        assert run.planner == "triage-playbook-1" and run.status == "completed" and run.latency_ms > 0
        by_kind = {s["kind"]: s for s in run.steps}
        # The rules engine already filed it correctly: the agent agrees rather than proposing a no-op.
        assert by_kind["category"]["outcome"] == "no_change"
        assert by_kind["next_action"]["outcome"] == "recorded"
        runs = client.get(f"{API}/tickets/{t['id']}/agent/runs", headers=auth(agent_a)).json()
        assert (
            runs[0]["steps"]
            and client.get(f"{API}/tickets/{t['id']}/agent/runs", headers=auth(customer_a)).status_code == 403
        )

    def test_invalid_proposals_are_stopped_and_hidden(self, client, db, org_a, agent_a, customer_a):
        train(db, org_a, customer_a, agent_a)
        # History says "Network & Connectivity", but the organization has since retired that category.
        db.query(Category).filter(Category.tenant_id == org_a.id, Category.name == "Network & Connectivity").delete()
        db.commit()
        t = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1])
        mislabel(db, t["id"])
        run_due_jobs()
        pred = db.query(AIPrediction).filter(AIPrediction.ticket_id == t["id"], AIPrediction.kind == "category").one()
        assert pred.status == "invalid" and "unknown category" in pred.evidence["policy"]
        shown = client.get(f"{API}/tickets/{t['id']}/ai", headers=auth(agent_a)).json()["predictions"]
        assert "category" not in {p["kind"] for p in shown}

    def test_failed_verification_rolls_the_change_back(self, client, db, org_a, agent_a, customer_a, monkeypatch):
        train(db, org_a, customer_a, agent_a)
        org_a.settings = {**org_a.settings, "ai_auto_apply_kinds": ["category"], "ai_auto_apply_threshold": 0.5}
        db.commit()
        spec = tools.TOOLS["set_category"]
        monkeypatch.setitem(
            tools.KIND_TO_TOOL,
            "category",
            tools.ToolSpec(
                spec.name,
                spec.kind,
                spec.risk,
                spec.input_model,
                spec.description,
                spec.validate,
                verify=lambda ctx, args: False,
            ),
        )
        t = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1])
        mislabel(db, t["id"])
        run_due_jobs()
        db.expire_all()
        assert db.get(Ticket, t["id"]).category == "Hardware"  # unchanged
        assert predictions(db, t["id"])["category"].status == "failed_verification"


class TestHighRiskActions:
    def test_vague_ticket_gets_a_request_for_details(self, client, db, org_a, manager_a, agent_a, customer_a):
        t = create_ticket(client, customer_a, title="Broken", description="It does not work at all today")
        run_due_jobs()
        pred = predictions(db, t["id"])["request_info"]
        assert pred.status == "proposed" and pred.source == "rules"  # high risk: waits for a person
        assign(client, manager_a, t["id"], agent_a.id)
        r = client.post(f"{API}/ai/predictions/{pred.id}/decision", headers=auth(agent_a), json={"decision": "accept"})
        assert r.status_code == 200
        db.expire_all()
        ticket = db.get(Ticket, t["id"])
        assert ticket.status == "waiting_for_customer"
        assert db.query(TicketComment).filter_by(ticket_id=t["id"], visibility="public").count() == 1

    def test_predicted_sla_breach_proposes_escalation(self, client, db, org_a, manager_a, agent_a, customer_a):
        train(db, org_a, customer_a, agent_a, n_each=12)  # 24 high tickets resolved in 3..14 h; 8 h SLA
        t = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1], priority="high")
        run_due_jobs()
        # Fresh ticket: its risk is just the priority's base rate (0.5) — no escalation proposed.
        assert "escalate" not in predictions(db, t["id"])
        # Six hours in and still open: 12 of the 16 comparable tickets breached (0.75 > 0.5 + 0.15).
        ticket = db.get(Ticket, t["id"])
        ticket.created_at = ticket.created_at - timedelta(hours=6, minutes=5)
        db.commit()
        client.post(f"{API}/tickets/{t['id']}/ai/analyze", headers=auth(manager_a))
        pred = predictions(db, t["id"])["escalate"]
        assert pred.status == "proposed" and "breach risk" in pred.value["reason"]
        r = client.post(
            f"{API}/ai/predictions/{pred.id}/decision", headers=auth(manager_a), json={"decision": "accept"}
        )
        assert r.status_code == 200
        db.expire_all()
        assert db.get(Ticket, t["id"]).status == "escalated"

    def test_published_article_becomes_a_reply_proposal(self, client, db, org_a, manager_a, agent_a, customer_a):
        doc = (
            b"# VPN keeps disconnecting\n\nIf the VPN client drops the tunnel on home wifi, update the client and "
            b"disable wifi power saving. The VPN tunnel then stays connected."
        )
        client.post(
            f"{API}/kb/documents",
            headers=auth(manager_a),
            data={"visibility": "public"},
            files={"file": ("vpn.md", io.BytesIO(doc), "text/markdown")},
        )
        run_due_jobs()
        t = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1])
        run_due_jobs()
        pred = predictions(db, t["id"])["reply"]
        assert pred.source == "rules" and "VPN keeps disconnecting" in pred.value["text"]
        r = client.post(f"{API}/ai/predictions/{pred.id}/decision", headers=auth(agent_a), json={"decision": "accept"})
        assert r.status_code == 200
        c = db.query(TicketComment).filter_by(ticket_id=t["id"], visibility="public").one()
        assert c.author_user_id == agent_a.id

    def test_internal_articles_are_never_offered_to_requesters(self, client, db, manager_a, customer_a):
        doc = b"# VPN keeps disconnecting\n\nInternal: reset the concentrator for VPN tunnel drops on home wifi."
        client.post(
            f"{API}/kb/documents",
            headers=auth(manager_a),
            data={"visibility": "internal"},
            files={"file": ("vpn.md", io.BytesIO(doc), "text/markdown")},
        )
        run_due_jobs()
        t = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1])
        run_due_jobs()
        assert "reply" not in predictions(db, t["id"])


class TestApprovalQueue:
    def test_queue_lists_waiting_items_across_tickets(self, client, db, org_a, agent_a, manager_a, customer_a):
        train(db, org_a, customer_a, agent_a)
        a = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1])
        b = create_ticket(client, customer_a, title="Broken", description="It does not work at all today")
        mislabel(db, a["id"])
        run_due_jobs()
        q = client.get(f"{API}/ai/queue", headers=auth(manager_a)).json()
        assert {i["ticket_id"] for i in q["items"]} == {a["id"], b["id"]}
        assert q["total"] == len(q["items"]) and q["by_risk"]["high"] >= 1
        high = client.get(f"{API}/ai/queue", params={"risk": "high"}, headers=auth(manager_a)).json()
        assert {i["risk"] for i in high["items"]} == {"high"}
        assert client.get(f"{API}/ai/queue", headers=auth(customer_a)).status_code == 403

    def test_bulk_decisions_apply_individual_permissions(self, client, db, org_a, agent_a, agent_a2, customer_a):
        train(db, org_a, customer_a, agent_a)
        t = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1])
        mislabel(db, t["id"])
        run_due_jobs()
        p = predictions(db, t["id"])
        r = client.post(
            f"{API}/ai/predictions/bulk-decision",
            headers=auth(agent_a2),
            json={"prediction_ids": [p["category"].id, p["team"].id], "decision": "accept"},
        ).json()
        assert r["decided"] == [p["category"].id]
        assert p["team"].id in {int(k) for k in r["failed"]}  # agents cannot route to other teams
        db.expire_all()
        assert db.get(Ticket, t["id"]).category == "Network & Connectivity"
