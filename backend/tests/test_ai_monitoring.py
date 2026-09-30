"""P13: drift and agreement monitoring."""

from collections import Counter
from datetime import timedelta

from app.ai import monitoring
from app.db.database import utcnow
from app.services import tickets as svc
from tests.conftest import auth


def make(db, requester, category, days_ago, n):
    for i in range(n):
        t = svc.create_ticket(
            db,
            requester=requester,
            title=f"{category} issue {i}",
            description="details here",
            created_at=utcnow() - timedelta(days=days_ago, hours=i % 20),
            analyze=False,
        )
        t.category = category
    db.commit()


def test_psi_is_zero_for_identical_mixes_and_large_for_a_shift():
    same = Counter({"a": 50, "b": 50})
    assert monitoring.psi(same, same) == 0
    assert monitoring.psi(Counter({"a": 90, "b": 10}), Counter({"a": 10, "b": 90})) > monitoring.PSI_ALERT


def test_category_shift_raises_an_alert(client, db, org_a, customer_a, manager_a):
    make(db, customer_a, "Hardware", days_ago=20, n=30)
    make(db, customer_a, "Network & Connectivity", days_ago=2, n=30)
    run = monitoring.run(db, org_a)
    db.commit()
    assert run.status == "alert" and run.metrics["category_psi"] > monitoring.PSI_ALERT
    assert any("category mix shifted" in a for a in run.alerts)
    body = client.get("/api/v1/analytics/ai-monitoring", headers=auth(manager_a)).json()
    assert body[0]["status"] == "alert"
    assert "nexadesk_ai_drift_alerts 1.0" in client.get("/metrics").text


def test_small_windows_are_insufficient_data(db, org_a, customer_a):
    make(db, customer_a, "Hardware", days_ago=20, n=5)
    make(db, customer_a, "Hardware", days_ago=2, n=5)
    run = monitoring.run(db, org_a)
    assert run.status == "insufficient_data" and "category_psi" not in run.metrics


def test_monitoring_is_per_organization(client, db, org_a, org_b, customer_a, admin_b):
    make(db, customer_a, "Hardware", days_ago=20, n=30)
    make(db, customer_a, "Security", days_ago=2, n=30)
    monitoring.run(db, org_a)
    db.commit()
    assert client.get("/api/v1/analytics/ai-monitoring", headers=auth(admin_b)).json() == []
