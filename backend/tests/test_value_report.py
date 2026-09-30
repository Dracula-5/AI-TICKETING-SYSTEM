from app.scripts import value_report
from app.services.jobs import run_due_jobs
from tests.conftest import auth, create_ticket
from tests.test_ai import VPN_QUERY, history, mislabel, predictions


def test_value_report_multiplies_measured_counts_by_stated_assumptions(
    client, db, org_a, agent_a, manager_a, customer_a, capsys
):
    org_a.settings = {**org_a.settings, "ai_min_history": 3}
    history(db, org_a, customer_a, agent_a)
    t = create_ticket(client, customer_a, title=VPN_QUERY[0], description=VPN_QUERY[1])
    mislabel(db, t["id"])
    run_due_jobs()
    p = predictions(db, t["id"])
    client.post(
        f"/api/v1/ai/predictions/{p['category'].id}/decision", headers=auth(manager_a), json={"decision": "accept"}
    )
    client.post(f"/api/v1/ai/predictions/{p['team'].id}/decision", headers=auth(manager_a), json={"decision": "reject"})
    code = value_report.main(
        [
            "--org",
            org_a.slug,
            "--triage-minutes",
            "3",
            "--reply-minutes",
            "5",
            "--hourly-cost",
            "40",
            "--currency",
            "EUR",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "| Triage/routing recommendations accepted or edited by agents | 1 |" in out  # the rejection does not count
    assert "0.1 agent-hours" in out and "≈ 2 EUR" in out  # 1 × 3 min = 0.05 h
    assert "not a measured saving" in out


def test_assumptions_are_required(org_a):
    import pytest

    with pytest.raises(SystemExit):
        value_report.main(["--org", org_a.slug])
