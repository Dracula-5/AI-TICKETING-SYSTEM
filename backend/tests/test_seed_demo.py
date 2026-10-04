from app.db.models import Feedback, KBDocument, Tenant, Ticket, TicketStatusHistory, User
from app.scripts import seed_demo
from app.scripts.seed_demo import ARTICLES, ORGS, PEOPLE, SEED_VERSION, TICKETS_PER_ORG, seed
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
    assert len(tickets) == 3 * TICKETS_PER_ORG and all(t.data_origin == "demo" for t in tickets)
    assert len({t.status for t in tickets}) >= 5
    assert len({t.title for t in tickets if t.tenant_id == tenants[0].id}) == TICKETS_PER_ORG  # no repeats in an org
    # Most of the history is finished work, the open backlog is recent.
    finished = [t for t in tickets if t.status in ("resolved", "closed")]
    assert len(finished) > len(tickets) / 2

    # Help articles, requester ratings and product feedback exist and are labelled demo.
    docs = db.query(KBDocument).all()
    assert len(docs) == 3 * len(ARTICLES) and all(d.data_origin == "demo" for d in docs)
    assert {d.visibility for d in docs} == {"public", "internal"}
    feedback = db.query(Feedback).all()
    assert all(f.data_origin == "demo" for f in feedback)
    ratings = [f for f in feedback if f.kind == "csat"]
    assert len(ratings) > 20 and all(1 <= f.rating <= 5 for f in ratings)
    assert all(f.ticket_id in {t.id for t in finished} for f in ratings)
    assert any(f.kind == "product" for f in feedback)

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
    monkeypatch.setattr(seed_demo, "TICKETS_PER_ORG", 6)
    seed()
    assert seed()["created"] == []
    again = seed(reset=True)
    assert len(again["created"]) == 3
    assert db.query(Tenant).count() == 3


def test_seed_recreates_demo_orgs_from_an_older_version_only(db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "Demo-Passw0rd!")
    monkeypatch.setattr(seed_demo, "TICKETS_PER_ORG", 6)
    seed()
    helix = db.query(Tenant).filter(Tenant.name == ORGS[0]["name"]).one()
    assert helix.settings["demo_seed_version"] == SEED_VERSION
    helix.settings = {k: v for k, v in helix.settings.items() if k != "demo_seed_version"}  # as seeded by v1
    stray = User(name="Visitor", email="visitor@example.com", hashed_password="x", role="customer", tenant_id=helix.id)
    db.add(stray)
    db.commit()
    old_id = helix.id

    result = seed()
    assert [o["org"] for o in result["created"]] == [ORGS[0]["name"]]
    db.expire_all()
    fresh = db.query(Tenant).filter(Tenant.name == ORGS[0]["name"]).one()
    assert fresh.id != old_id and fresh.slug == "helix-health-demo"
    assert db.query(User).filter(User.email == "visitor@example.com").count() == 0
    assert db.query(Tenant).count() == 3
