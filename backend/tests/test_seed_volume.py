import json

from app.db.models import Tenant, Ticket, TicketStatusHistory
from app.scripts import seed_volume


def test_seeds_labelled_synthetic_volume_and_tokens(db, tmp_path):
    out = tmp_path / "tokens.json"
    assert seed_volume.main(["--tickets", "300", "--tokens-out", str(out)]) == 0
    tenant = db.query(Tenant).filter(Tenant.name == seed_volume.ORG_NAME).one()
    assert tenant.is_demo and tenant.data_origin == "synthetic"
    tickets = db.query(Ticket).filter(Ticket.tenant_id == tenant.id).all()
    assert len(tickets) == 300 and tenant.ticket_seq == 300
    assert {t.data_origin for t in tickets} == {"synthetic"}
    assert sorted(t.number for t in tickets) == list(range(1, 301))
    assert db.query(TicketStatusHistory).filter(TicketStatusHistory.tenant_id == tenant.id).count() == 300
    tokens = json.loads(out.read_text())
    assert len(tokens["users"]["customer"]) == 300 and len(tokens["users"]["agent"]) == 20
    # Extending keeps numbering unique; --reset starts over.
    seed_volume.main(["--tickets", "50"])
    assert db.query(Ticket).filter(Ticket.tenant_id == tenant.id).count() == 350
    seed_volume.main(["--tickets", "10", "--reset"])
    assert db.query(Ticket).filter(Ticket.tenant_id == tenant.id).count() == 10


def test_tokens_authenticate(client, db, tmp_path):
    out = tmp_path / "tokens.json"
    seed_volume.main(["--tickets", "5", "--tokens-out", str(out)])
    token = json.loads(out.read_text())["users"]["agent"][0]["token"]
    r = client.get("/api/v1/tickets", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["total"] == 5
