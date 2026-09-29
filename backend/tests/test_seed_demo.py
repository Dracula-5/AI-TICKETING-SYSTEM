from app.db.models import Tenant, Ticket, TicketStatusHistory, User
from app.scripts.seed_demo import ORGS, PEOPLE, seed
from tests.conftest import auth


def test_seed_creates_labelled_demo_orgs(db, client, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "Demo-Passw0rd!")
    result = seed()
    assert len(result["created"]) == len(ORGS) == 3

    tenants = db.query(Tenant).all()
    assert all(t.is_demo and t.data_origin == "demo" for t in tenants)
    users = db.query(User).all()
    assert len(users) == 3 * len(PEOPLE) >= 10
    assert all(u.data_origin == "demo" for u in users)
    assert {u.role for u in users} == {"org_admin", "manager", "agent", "analyst", "customer"}
    tickets = db.query(Ticket).all()
    assert len(tickets) == 3 * 18 and all(t.data_origin == "demo" for t in tickets)
    assert len({t.status for t in tickets}) >= 5

    # Every ticket starts with a creation row and history never goes backwards.
    for t in tickets[:10]:
        rows = (
            db.query(TicketStatusHistory)
            .filter(TicketStatusHistory.ticket_id == t.id)
            .order_by(TicketStatusHistory.id)
            .all()
        )
        assert rows[0].from_status is None
        times = [r.created_at for r in rows]
        assert times == sorted(times)

    # Demo accounts work, and their dashboards say "demo".
    admin = next(u for u in users if u.role == "org_admin")
    login = client.post("/api/v1/auth/login", data={"username": admin.email, "password": "Demo-Passw0rd!"})
    assert login.status_code == 200
    assert client.get("/api/v1/analytics/overview", headers=auth(admin)).json()["data_origin"] == "demo"


def test_seed_is_idempotent_and_resettable(db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "Demo-Passw0rd!")
    seed()
    assert seed()["created"] == []
    again = seed(reset=True)
    assert len(again["created"]) == 3
    assert db.query(Tenant).count() == 3
