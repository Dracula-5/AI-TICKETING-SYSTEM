from app.db.models import AuditLog
from tests.conftest import auth, create_ticket, make_org, make_user, team_id

API = "/api/v1"


class TestTeams:
    def test_crud_and_membership(self, client, db, admin_a, agent_a, agent_a2):
        created = client.post(
            f"{API}/teams", json={"name": "Networking", "description": "LAN/WAN"}, headers=auth(admin_a)
        )
        assert created.status_code == 201
        tid = created.json()["id"]
        assert client.post(f"{API}/teams", json={"name": "Networking"}, headers=auth(admin_a)).status_code == 409

        renamed = client.patch(f"{API}/teams/{tid}", json={"name": "Network Ops"}, headers=auth(admin_a)).json()
        assert renamed["name"] == "Network Ops"

        members = client.put(
            f"{API}/teams/{tid}/members", json={"user_ids": [agent_a.id, agent_a2.id]}, headers=auth(admin_a)
        ).json()
        assert members["member_ids"] == sorted([agent_a.id, agent_a2.id])
        members = client.put(
            f"{API}/teams/{tid}/members", json={"user_ids": [agent_a.id]}, headers=auth(admin_a)
        ).json()
        assert members["member_ids"] == [agent_a.id]
        audit = db.query(AuditLog).filter(AuditLog.action == "team.members").order_by(AuditLog.id.desc()).first()
        assert audit.changes == {"added": [], "removed": [agent_a2.id]}

        assert client.delete(f"{API}/teams/{tid}", headers=auth(admin_a)).status_code == 200
        assert all(t["id"] != tid for t in client.get(f"{API}/teams", headers=auth(admin_a)).json())

    def test_customers_cannot_be_team_members(self, client, db, org_a, admin_a, customer_a):
        tid = team_id(db, org_a, "Service Desk")
        r = client.put(f"{API}/teams/{tid}/members", json={"user_ids": [customer_a.id]}, headers=auth(admin_a))
        assert r.status_code == 422

    def test_deleting_a_team_unroutes_its_tickets(self, client, db, org_a, admin_a, agent_a, customer_a):
        t = create_ticket(client, customer_a, title="VPN down", description="vpn")
        infra = team_id(db, org_a, "Infrastructure")
        assert t["team"]["id"] == infra
        client.delete(f"{API}/teams/{infra}", headers=auth(admin_a))
        assert client.get(f"{API}/tickets/{t['id']}", headers=auth(agent_a)).json()["team"] is None

    def test_demo_org_cannot_delete_teams(self, client, db):
        demo = make_org(db, "Demo Org", is_demo=True, data_origin="demo")
        admin = make_user(db, demo, "org_admin", "admin@demo.example.com")
        tid = team_id(db, demo, "Security")
        assert client.delete(f"{API}/teams/{tid}", headers=auth(admin)).status_code == 403


class TestCategories:
    def test_create_update_and_route(self, client, db, org_a, admin_a, customer_a):
        security = team_id(db, org_a, "Security")
        r = client.post(
            f"{API}/categories",
            json={"name": "Badge Access", "keywords": ["Badge", "turnstile", "badge"], "default_team_id": security},
            headers=auth(admin_a),
        )
        assert r.status_code == 201
        cat = r.json()
        assert cat["keywords"] == ["badge", "turnstile"]

        t = create_ticket(client, customer_a, title="Turnstile rejects me", description="The turnstile beeps red")
        assert t["category"] == "Badge Access" and t["team"]["id"] == security

        r = client.put(
            f"{API}/categories/{cat['id']}",
            json={"name": "Badge Access", "keywords": [], "is_active": False},
            headers=auth(admin_a),
        )
        assert r.status_code == 200 and r.json()["is_active"] is False
        names = [c["name"] for c in client.get(f"{API}/categories", headers=auth(customer_a)).json()]
        assert "Badge Access" not in names

    def test_duplicate_and_foreign_team_rejected(self, client, db, org_b, admin_a):
        assert client.post(f"{API}/categories", json={"name": "Hardware"}, headers=auth(admin_a)).status_code == 409
        foreign = team_id(db, org_b, "Security")
        r = client.post(f"{API}/categories", json={"name": "X Cat", "default_team_id": foreign}, headers=auth(admin_a))
        assert r.status_code == 404


class TestOrganizationSettings:
    def test_update_name_and_settings(self, client, db, admin_a):
        current = client.get(f"{API}/organizations/me", headers=auth(admin_a)).json()
        r = client.patch(
            f"{API}/organizations/me",
            json={"name": "Acme Corporation", "settings": {**current["settings"], "auto_close_days": 5}},
            headers=auth(admin_a),
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Acme Corporation" and r.json()["settings"]["auto_close_days"] == 5
        entry = db.query(AuditLog).filter(AuditLog.action == "org.update").one()
        assert "name" in entry.changes and "settings" in entry.changes

    def test_invalid_settings_rejected(self, client, admin_a):
        r = client.patch(
            f"{API}/organizations/me",
            json={"settings": {"portal_allowed_domains": ["not a domain"]}},
            headers=auth(admin_a),
        )
        assert r.status_code == 422

    def test_profile_update(self, client, agent_a):
        r = client.patch(f"{API}/users/me", json={"name": "Agent Smith"}, headers=auth(agent_a))
        assert r.status_code == 200 and r.json()["name"] == "Agent Smith"


class TestInvitationsAdmin:
    def test_reinvite_replaces_and_revoke(self, client, admin_a):
        first = client.post(
            f"{API}/organizations/me/invitations",
            json={"email": "x@acme.example.com", "role": "agent"},
            headers=auth(admin_a),
        ).json()
        second = client.post(
            f"{API}/organizations/me/invitations",
            json={"email": "x@acme.example.com", "role": "manager"},
            headers=auth(admin_a),
        ).json()
        pending = client.get(f"{API}/organizations/me/invitations", headers=auth(admin_a)).json()
        assert [i["id"] for i in pending] == [second["id"]]
        token = first["invite_url"].split("token=")[1]
        assert client.get(f"{API}/auth/invitations/{token}").status_code == 400

        assert (
            client.delete(f"{API}/organizations/me/invitations/{second['id']}", headers=auth(admin_a)).status_code
            == 200
        )
        token = second["invite_url"].split("token=")[1]
        r = client.post(
            f"{API}/auth/accept-invitation", json={"token": token, "name": "X", "password": "Str0ng-Passw0rd"}
        )
        assert r.status_code == 400

    def test_cannot_invite_existing_account(self, client, admin_a, agent_b):
        r = client.post(
            f"{API}/organizations/me/invitations", json={"email": agent_b.email, "role": "agent"}, headers=auth(admin_a)
        )
        assert r.status_code == 409


class TestHealth:
    def test_liveness(self, client):
        assert client.get("/health").json() == {"status": "ok"}

    def test_readiness_reports_schema_state(self, client):
        # Tests build the schema with create_all, so there is no alembic_version table.
        body = client.get("/ready").json()
        assert body["database"] == "ok" and body["status"] == "ready"
