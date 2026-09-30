"""AI-assisted triage: recommendations, human decisions, policy, isolation, jobs.

Uses the deterministic `test-hashing` embedder (conftest), so the numbers here
test behaviour, not model quality — model quality is measured in experiments/.
"""

from datetime import timedelta

import pytest

from app.ai.policy import decide
from app.db.database import utcnow
from app.db.models import AIPrediction, AuditLog, Job, Ticket, TicketEmbedding
from app.services import jobs
from app.services import tickets as svc
from app.services.jobs import run_due_jobs
from tests.conftest import auth, create_ticket, make_user, team_id

API = "/api/v1"

VPN = [
    (
        "VPN keeps disconnecting on home wifi",
        "The VPN client drops the tunnel every few minutes when on home wifi network",
    ),
    ("Cannot connect to VPN", "VPN client shows error 809 and the tunnel will not connect to the network"),
    ("VPN tunnel drops", "Our VPN tunnel drops for remote staff; network connection resets"),
]
VPN_QUERY = ("VPN disconnects from home", "VPN tunnel keeps dropping on my home wifi network")
PRINTER = [
    ("Printer jams on floor 2", "The printer on floor 2 jams on every duplex print job, paper stuck"),
    ("Printer not printing", "Office printer queue stuck, printer shows paper jam error"),
]


def history(db, org, requester, resolver, n_each=6):
    """Resolved tickets whose labels the AI can learn from."""
    network, hardware = team_id(db, org, "Infrastructure"), team_id(db, org, "Service Desk")
    made = []
    for i in range(n_each):
        for (title, desc), cat, team in [
            (VPN[i % 3], "Network & Connectivity", network),
            (PRINTER[i % 2], "Hardware", hardware),
        ]:
            t = svc.create_ticket(
                db,
                requester=requester,
                title=f"{title} ({i})",
                description=desc,
                priority="high",
                created_at=utcnow() - timedelta(days=10, hours=i),
            )
            t.category, t.team_id, t.assigned_to_user_id = cat, team, resolver.id
            t.status, t.resolved_at = "resolved", t.created_at + timedelta(hours=3 + i)
            made.append(t)
    db.commit()
    run_due_jobs()  # embeds the history (and records its own recommendations)
    return made


@pytest.fixture()
def trained_org(db, org_a, agent_a, customer_a):
    # The hashing test embedder is far cruder than a real model, so fewer
    # neighbours clear the similarity floor; lower the org's history minimum.
    org_a.settings = {**org_a.settings, "ai_min_history": 3}
    history(db, org_a, customer_a, agent_a)
    return org_a


def mislabel(db, ticket_id):
    """The rules engine already files VPN tickets correctly; start from a wrong
    category/team so the AI's recommendation is a real change."""
    ticket = db.get(Ticket, ticket_id)
    ticket.category, ticket.team_id = "Hardware", team_id(db, ticket.tenant, "Service Desk")
    db.commit()


def predictions(db, ticket_id):
    return {
        p.kind: p
        for p in db.query(AIPrediction).filter(AIPrediction.ticket_id == ticket_id, AIPrediction.status != "superseded")
    }


class TestTriageJob:
    def test_ticket_creation_enqueues_ai_triage_once(self, client, db, customer_a):
        t = create_ticket(client, customer_a)
        job = db.query(Job).filter(Job.dedupe_key == f"ai.triage:{t['id']}").one()
        assert job.kind == "ai.triage" and job.status == "queued"
        assert jobs.enqueue(db, "ai.triage", {"ticket_id": t["id"]}, dedupe_key=f"ai.triage:{t['id']}") is None

    def test_recommendations_come_from_similar_resolved_tickets(self, client, db, trained_org, agent_a, customer_a):
        t = create_ticket(
            client,
            customer_a,
            title="VPN disconnects from home",
            description="VPN tunnel keeps dropping on my home wifi network",
        )
        run_due_jobs()
        preds = predictions(db, t["id"])
        assert preds["category"].value == {"category": "Network & Connectivity"}
        assert preds["category"].confidence > 0.5 and preds["category"].source == "ai"
        assert preds["team"].value["team"] == "Infrastructure"
        assert preds["assignee"].value["user_id"] == agent_a.id
        assert "resolution_time" not in preds  # 12 resolved same-priority tickets < MIN_STAT_SAMPLE
        assert preds["next_action"].source == "rules"
        similar = preds["category"].evidence["similar_tickets"]
        assert similar and all("VPN" in s["title"] for s in similar[:3])
        assert db.get(TicketEmbedding, t["id"]) is not None

    def test_thin_history_means_no_ai_vote(self, client, db, customer_a):
        t = create_ticket(client, customer_a)
        run_due_jobs()
        preds = predictions(db, t["id"])
        assert "category" not in preds and "team" not in preds  # rules triage stands
        assert "next_action" in preds

    def test_possible_duplicate_of_open_ticket(self, client, db, org_a, customer_a):
        first = create_ticket(
            client,
            customer_a,
            title="Printer jams on floor 2",
            description="The printer on floor 2 jams on every duplex job",
        )
        run_due_jobs()
        second = create_ticket(
            client,
            customer_a,
            title="Printer jams on floor 2",
            description="The printer on floor 2 jams on every duplex job",
        )
        run_due_jobs()
        dup = predictions(db, second["id"])["duplicate"]
        assert dup.value["ticket_id"] == first["id"]
        assert dup.evidence["candidates"][0]["same_requester"] is True

    def test_sla_risk_needs_enough_history(self, client, db, org_a, agent_a, customer_a):
        history(db, org_a, customer_a, agent_a, n_each=12)  # 24 resolved "high" tickets
        t = create_ticket(client, customer_a, priority="high")
        run_due_jobs()
        preds = predictions(db, t["id"])
        risk = preds["sla_risk"]
        assert 0 <= risk.value["breach_probability"] <= 1 and risk.evidence["n"] >= 10
        assert risk.source == "statistics" and risk.value["base_rate"] == 0.5
        eta = preds["resolution_time"]  # median/IQR of the 24 same-priority tickets (3..14 h)
        assert eta.source == "statistics" and eta.evidence["n"] == 24 and 8 <= eta.value["hours"] <= 9


class TestHumanDecisions:
    def _ticket_with_predictions(self, client, db, customer_a):
        t = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1])
        mislabel(db, t["id"])
        run_due_jobs()
        return t, predictions(db, t["id"])

    def test_accept_applies_and_attributes_to_ai(self, client, db, trained_org, manager_a, customer_a):
        t, preds = self._ticket_with_predictions(client, db, customer_a)
        r = client.post(
            f"{API}/ai/predictions/{preds['category'].id}/decision",
            json={"decision": "accept"},
            headers=auth(manager_a),
        )
        assert r.status_code == 200 and r.json()["status"] == "accepted"
        ticket = db.get(Ticket, t["id"])
        db.refresh(ticket)
        assert ticket.category == "Network & Connectivity" and ticket.triage_source == "ai"
        assert db.query(AuditLog).filter(AuditLog.action == "ai.accept").count() == 1

    def test_edit_records_the_human_value(self, client, db, trained_org, manager_a, customer_a):
        _, preds = self._ticket_with_predictions(client, db, customer_a)
        r = client.post(
            f"{API}/ai/predictions/{preds['category'].id}/decision",
            json={"decision": "edit", "value": {"category": "Security"}},
            headers=auth(manager_a),
        )
        assert r.status_code == 200 and r.json()["final_value"] == {"category": "Security"}

    def test_reject_changes_nothing(self, client, db, trained_org, manager_a, customer_a):
        t, preds = self._ticket_with_predictions(client, db, customer_a)
        before = db.get(Ticket, t["id"]).category
        r = client.post(
            f"{API}/ai/predictions/{preds['team'].id}/decision", json={"decision": "reject"}, headers=auth(manager_a)
        )
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        db.expire_all()
        assert db.get(Ticket, t["id"]).category == before

    def test_decisions_are_final(self, client, db, trained_org, manager_a, customer_a):
        _, preds = self._ticket_with_predictions(client, db, customer_a)
        url = f"{API}/ai/predictions/{preds['priority'].id}/decision"
        assert client.post(url, json={"decision": "reject"}, headers=auth(manager_a)).status_code == 200
        assert client.post(url, json={"decision": "accept"}, headers=auth(manager_a)).status_code == 409

    def test_agents_cannot_route_to_other_people(self, client, db, trained_org, agent_a2, customer_a):
        _, preds = self._ticket_with_predictions(client, db, customer_a)
        r = client.post(
            f"{API}/ai/predictions/{preds['team'].id}/decision", json={"decision": "accept"}, headers=auth(agent_a2)
        )
        assert r.status_code == 403

    def test_requesters_never_see_ai(self, client, db, trained_org, customer_a):
        t, _ = self._ticket_with_predictions(client, db, customer_a)
        assert client.get(f"{API}/tickets/{t['id']}/ai", headers=auth(customer_a)).status_code == 403

    def test_staff_view_and_synchronous_endpoints(self, client, db, trained_org, agent_a, customer_a):
        t, _ = self._ticket_with_predictions(client, db, customer_a)
        body = client.get(f"{API}/tickets/{t['id']}/ai", headers=auth(agent_a)).json()
        assert body["status"] == "ready" and {p["kind"] for p in body["predictions"]} >= {"category", "team"}
        classify = client.post(f"{API}/tickets/{t['id']}/classify", headers=auth(agent_a)).json()
        assert {p["kind"] for p in classify["predictions"]} <= {"category", "priority"}
        route = client.post(f"{API}/tickets/{t['id']}/route", headers=auth(agent_a)).json()
        assert {p["kind"] for p in route["predictions"]} <= {"team", "assignee"}


class TestPolicy:
    def test_policy_rules(self, org_a):
        org_a.settings = {**org_a.settings, "ai_auto_apply_kinds": ["category", "team"], "ai_auto_apply_threshold": 0.8}
        assert decide(org_a, "category", 0.95).auto_apply
        assert not decide(org_a, "category", 0.7).auto_apply
        assert not decide(org_a, "category", None).auto_apply
        assert not decide(org_a, "priority", 0.99).auto_apply  # not enabled for this org
        assert not decide(org_a, "duplicate", 1.0).auto_apply  # high risk: never
        assert not decide(org_a, "reply", 1.0).auto_apply
        assert not decide(org_a, "summary", 1.0).auto_apply

    def test_auto_apply_then_human_override(self, client, db, trained_org, manager_a, customer_a):
        trained_org.settings = {
            **trained_org.settings,
            "ai_auto_apply_kinds": ["category"],
            "ai_auto_apply_threshold": 0.5,
        }
        db.commit()
        t = create_ticket(
            client, customer_a, title="VPN tunnel drops again", description="Remote VPN tunnel drops; network resets"
        )
        mislabel(db, t["id"])
        run_due_jobs()
        pred = predictions(db, t["id"])["category"]
        assert pred.status == "auto_applied"
        ticket = db.get(Ticket, t["id"])
        db.refresh(ticket)
        assert ticket.category == "Network & Connectivity" and ticket.triage_source == "ai"
        assert db.query(AuditLog).filter(AuditLog.action == "ticket.update", AuditLog.actor_type == "ai").count() >= 1

        client.patch(f"{API}/tickets/{t['id']}", json={"category": "Security"}, headers=auth(manager_a))
        db.expire_all()
        assert db.get(AIPrediction, pred.id).status == "overridden"

        perf = client.get(f"{API}/analytics/ai-performance", headers=auth(manager_a)).json()
        cat = next(k for k in perf["by_kind"] if k["kind"] == "category")
        assert cat["overridden"] >= 1 and cat["automation_false_positive_rate"] is not None


class TestIsolation:
    def test_similarity_search_never_crosses_orgs(self, client, db, trained_org, org_b, customer_b):
        t = create_ticket(
            client,
            customer_b,
            title="VPN keeps disconnecting on home wifi",
            description="The VPN client drops the tunnel every few minutes when on home wifi network",
        )
        run_due_jobs()
        preds = predictions(db, t["id"])
        assert "category" not in preds and "duplicate" not in preds  # org A's history is invisible
        for p in preds.values():
            for s in (p.evidence or {}).get("similar_tickets", []):
                assert db.get(Ticket, s["ticket_id"]).tenant_id == org_b.id

    def test_foreign_predictions_are_not_found(self, client, db, trained_org, admin_b, customer_a):
        t = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1])
        run_due_jobs()
        pred = predictions(db, t["id"])["category"]
        r = client.post(f"{API}/ai/predictions/{pred.id}/decision", json={"decision": "reject"}, headers=auth(admin_b))
        assert r.status_code == 404


class TestJobQueue:
    def test_failing_job_retries_then_dead_letters(self, db):
        calls = []

        @jobs.handler("test.boom")
        def boom(_db, _payload):
            calls.append(1)
            raise RuntimeError("nope")

        job = jobs.enqueue(db, "test.boom", {}, max_attempts=3)
        db.commit()
        for _ in range(3):
            run_due_jobs()
            db.expire_all()
            db.query(Job).filter(Job.id == job.id, Job.status == "failed").update(
                {Job.run_after: utcnow() - timedelta(seconds=1)}
            )
            db.commit()
        final = db.get(Job, job.id)
        assert final.status == "dead" and final.attempts == 3 and "nope" in final.last_error
        assert len(calls) == 3

    def test_unknown_kind_is_dead_lettered_not_crashing(self, db):
        job = jobs.enqueue(db, "does.not.exist", {}, max_attempts=1)
        db.commit()
        run_due_jobs()
        db.expire_all()
        assert db.get(Job, job.id).status == "dead"

    def test_stale_running_job_is_reclaimed(self, db):
        @jobs.handler("test.ok")
        def ok(_db, payload):
            return {"echo": payload["x"]}

        job = jobs.enqueue(db, "test.ok", {"x": 1})
        db.commit()
        db.query(Job).filter(Job.id == job.id).update(
            {Job.status: "running", Job.started_at: utcnow() - timedelta(hours=1), Job.attempts: 1}
        )
        db.commit()
        run_due_jobs()
        db.expire_all()
        done = db.get(Job, job.id)
        assert done.status == "done" and done.result == {"echo": 1} and done.attempts == 2


def test_org_admin_can_configure_ai_policy(client, admin_a):
    current = client.get(f"{API}/organizations/me", headers=auth(admin_a)).json()["settings"]
    r = client.patch(
        f"{API}/organizations/me",
        headers=auth(admin_a),
        json={"settings": {**current, "ai_auto_apply_kinds": ["category"], "ai_auto_apply_threshold": 0.95}},
    )
    assert r.status_code == 200 and r.json()["settings"]["ai_auto_apply_kinds"] == ["category"]
    bad = client.patch(
        f"{API}/organizations/me",
        headers=auth(admin_a),
        json={"settings": {**current, "ai_auto_apply_kinds": ["duplicate"]}},
    )
    assert bad.status_code == 422


def test_make_user_helper_still_works(db, org_a):
    assert make_user(db, org_a, "agent", "x@acme.example.com").id
