"""P9: CSAT, product feedback and pilot metrics (computed, sample-size aware,
demo data labelled)."""

from app.db.models import Feedback
from app.scripts import pilot_report
from app.services import pilot
from tests.conftest import assign, auth, create_ticket, move

API = "/api/v1"


def resolved_ticket(client, manager, agent, customer):
    t = create_ticket(client, customer)
    assign(client, manager, t["id"], agent.id)
    move(client, agent, t["id"], "in_progress")
    move(client, agent, t["id"], "resolved", resolution_summary="Replaced the toner")
    return t


def test_requester_rates_a_resolved_ticket_once(client, db, manager_a, agent_a, customer_a):
    t = resolved_ticket(client, manager_a, agent_a, customer_a)
    r = client.post(f"{API}/tickets/{t['id']}/csat", headers=auth(customer_a), json={"rating": 4, "comment": "Fast"})
    assert r.status_code == 200 and r.json()["rating"] == 4
    client.post(f"{API}/tickets/{t['id']}/csat", headers=auth(customer_a), json={"rating": 5})
    rows = db.query(Feedback).filter_by(ticket_id=t["id"], kind="csat").all()
    assert len(rows) == 1 and rows[0].rating == 5  # updated, not duplicated


def test_only_the_requester_rates_and_only_when_resolved(client, manager_a, agent_a, customer_a, customer_a2):
    open_ticket = create_ticket(client, customer_a)
    assert (
        client.post(f"{API}/tickets/{open_ticket['id']}/csat", headers=auth(customer_a), json={"rating": 3}).status_code
        == 409
    )
    t = resolved_ticket(client, manager_a, agent_a, customer_a)
    assert (
        client.post(f"{API}/tickets/{t['id']}/csat", headers=auth(customer_a2), json={"rating": 1}).status_code == 404
    )
    assert client.post(f"{API}/tickets/{t['id']}/csat", headers=auth(agent_a), json={"rating": 5}).status_code == 404
    assert client.post(f"{API}/tickets/{t['id']}/csat", headers=auth(customer_a), json={"rating": 6}).status_code == 422


def test_product_feedback_is_visible_to_managers_only(client, agent_a, manager_a, customer_a):
    r = client.post(f"{API}/feedback", headers=auth(customer_a), json={"comment": "Search is great", "page": "/kb"})
    assert r.status_code == 201
    listed = client.get(f"{API}/feedback", headers=auth(manager_a)).json()
    assert [f["comment"] for f in listed] == ["Search is great"]
    assert client.get(f"{API}/feedback", headers=auth(agent_a)).status_code == 403


def test_pilot_metrics_refuse_small_samples(client, db, org_a, manager_a, agent_a, customer_a):
    for rating in (5, 4, 2):
        t = resolved_ticket(client, manager_a, agent_a, customer_a)
        client.post(f"{API}/tickets/{t['id']}/csat", headers=auth(customer_a), json={"rating": rating})
    m = client.get(f"{API}/analytics/pilot", headers=auth(manager_a)).json()
    assert m["satisfaction"]["csat_responses"] == 3
    assert m["satisfaction"]["csat_mean"] is None  # 3 < MIN_SAMPLE: "not enough data", not 3.67
    assert m["tickets"]["created"] == 3 and m["tickets"]["resolved"] == 3
    for _ in range(2):
        t = resolved_ticket(client, manager_a, agent_a, customer_a)
        client.post(f"{API}/tickets/{t['id']}/csat", headers=auth(customer_a), json={"rating": 5})
    m = pilot.compute(db, org_a)
    assert m["satisfaction"]["csat_mean"] == 4.2 and m["satisfaction"]["csat_share_4_or_5"] == 0.8


def test_report_labels_demo_organizations(db, org_a, capsys):
    org_a.is_demo, org_a.data_origin = True, "demo"
    db.commit()
    assert pilot_report.main(["--org", org_a.slug]) == 0
    out = capsys.readouterr().out
    assert "These are not real-usage results" in out and "not enough data" in out
