"""Platform console: aggregates across organizations, no ticket content,
organization deletion, and the environment-driven platform administrator."""

from app.core.security import verify_password
from app.db.models import AuditLog, Tenant, Ticket, User
from app.scripts import platform_admin as bootstrap
from tests.conftest import PASSWORD, assign, auth, create_ticket, make_org, make_user, move

API = "/api/v1"


class TestConsole:
    def test_every_route_requires_the_platform_role(self, client, admin_a, org_a):
        for method, path in [
            ("get", "/platform/overview"),
            ("get", "/platform/organizations"),
            ("get", "/platform/users"),
            ("delete", f"/platform/organizations/{org_a.id}?confirm={org_a.slug}"),
        ]:
            assert getattr(client, method)(f"{API}{path}").status_code == 401
            assert getattr(client, method)(f"{API}{path}", headers=auth(admin_a)).status_code == 403
        assert client.get(f"{API}/tickets", headers=auth(admin_a)).status_code == 200  # org untouched

    def test_overview_reports_activity_and_system_state(self, client, platform_admin, customer_a):
        create_ticket(client, customer_a)
        body = client.get(f"{API}/platform/overview", headers=auth(platform_admin)).json()
        assert body["open_tickets"] == 1 and body["tickets_7d"] == 1 and body["sla_breached_open"] == 0
        assert body["environment"] == "test" and body["text_generation"] is False
        assert isinstance(body["jobs_by_status"], dict) and isinstance(body["emails_by_status"], dict)

    def test_organizations_are_aggregates_per_org(self, client, db, platform_admin, customer_a, agent_a, customer_b):
        create_ticket(client, customer_a)
        create_ticket(client, customer_a)
        rows = client.get(f"{API}/platform/organizations", headers=auth(platform_admin)).json()
        by_name = {r["name"]: r for r in rows}
        a = by_name[customer_a.tenant.name]
        assert a["users"] == 2 and a["tickets"] == 2 and a["open_tickets"] == 2 and a["tickets_7d"] == 2
        assert a["last_ticket_at"] is not None and a["is_demo"] is False
        b = by_name[customer_b.tenant.name]
        assert b["users"] == 1 and b["tickets"] == 0 and b["last_ticket_at"] is None
        # Aggregates only: no ticket text reaches the platform console.
        assert "title" not in a and "description" not in a

    def test_users_lists_recent_accounts_with_their_organization(self, client, platform_admin, customer_a):
        rows = client.get(f"{API}/platform/users", headers=auth(platform_admin)).json()
        emails = {r["email"]: r for r in rows}
        assert emails[customer_a.email]["organization"] == customer_a.tenant.name
        assert emails[platform_admin.email]["organization"] is None
        assert "hashed_password" not in rows[0]

    def test_delete_needs_the_slug_and_removes_everything(
        self, client, db, platform_admin, customer_a, agent_a, admin_a, customer_b
    ):
        # An organization with every kind of activity hanging off it.
        ticket = create_ticket(client, customer_a)
        tid = ticket["id"]
        client.post(f"{API}/auth/login", data={"username": customer_a.email, "password": "wrong-password"})
        assert (
            client.post(f"{API}/auth/login", data={"username": agent_a.email, "password": PASSWORD}).status_code == 200
        )
        assign(client, admin_a, tid, agent_a.id)
        move(client, agent_a, tid, "acknowledged")
        move(client, agent_a, tid, "in_progress")
        client.post(f"{API}/tickets/{tid}/comments", json={"content": "Looking into it"}, headers=auth(agent_a))
        move(client, agent_a, tid, "resolved", resolution_summary="Fixed")
        assert client.post(f"{API}/tickets/{tid}/csat", json={"rating": 5}, headers=auth(customer_a)).status_code == 200
        upload = client.post(
            f"{API}/kb/documents",
            files={"file": ("vpn.md", b"# VPN\n\nRestart the client.", "text/markdown")},
            data={"visibility": "public"},
            headers=auth(admin_a),
        )
        assert upload.status_code == 202
        client.post(
            f"{API}/organizations/me/invitations",
            json={"email": "new.agent@acme.example.com", "role": "agent"},
            headers=auth(admin_a),
        )
        client.get(f"{API}/kb/search", params={"q": "vpn"}, headers=auth(customer_a))
        org_id, slug = customer_a.tenant_id, customer_a.tenant.slug
        headers = auth(platform_admin)
        assert client.delete(f"{API}/platform/organizations/{org_id}?confirm=wrong", headers=headers).status_code == 400
        assert client.delete(f"{API}/platform/organizations/999999?confirm=x", headers=headers).status_code == 404
        assert db.query(Tenant).count() == 2

        assert (
            client.delete(f"{API}/platform/organizations/{org_id}?confirm={slug}", headers=headers).status_code == 204
        )
        db.expire_all()
        assert db.get(Tenant, org_id) is None
        assert db.query(User).filter(User.tenant_id == org_id).count() == 0
        assert db.query(Ticket).filter(Ticket.tenant_id == org_id).count() == 0
        assert db.get(Tenant, customer_b.tenant_id) is not None  # other organizations untouched
        entry = db.query(AuditLog).filter(AuditLog.action == "platform.org.delete").one()
        assert entry.tenant_id is None and entry.changes["slug"] == slug and entry.changes["tickets"] == 1


class TestBootstrap:
    PASSWORD = "Platform-Adm1n-pass"

    def test_creates_a_platform_admin_who_can_sign_in(self, client, db):
        assert bootstrap.ensure("Ops@NexaDesk.example.com", self.PASSWORD) == "created"
        user = db.query(User).filter(User.email == "ops@nexadesk.example.com").one()
        assert user.role == "platform_admin" and user.tenant_id is None and user.email_verified_at is not None
        login = client.post(f"{API}/auth/login", data={"username": user.email, "password": self.PASSWORD})
        assert login.status_code == 200
        token = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert client.get(f"{API}/platform/overview", headers=token).status_code == 200

    def test_is_idempotent_and_rotates_the_password(self, db):
        bootstrap.ensure("ops@nexadesk.example.com", self.PASSWORD)
        assert bootstrap.ensure("ops@nexadesk.example.com", self.PASSWORD) == "unchanged"
        assert bootstrap.ensure("ops@nexadesk.example.com", "Another-Passw0rd") == "password updated"
        user = db.query(User).filter(User.email == "ops@nexadesk.example.com").one()
        assert verify_password("Another-Passw0rd", user.hashed_password)
        assert db.query(User).count() == 1

    def test_refuses_weak_passwords_and_organization_members(self, db):
        for bad in ("short", "alllowercase123", "NoDigitsHere!"):
            try:
                bootstrap.ensure("ops@nexadesk.example.com", bad)
            except ValueError:
                continue
            raise AssertionError(f"accepted weak password {bad!r}")
        member = make_user(db, make_org(db), "org_admin", "admin@acme.example.com")
        try:
            bootstrap.ensure(member.email, self.PASSWORD)
        except ValueError as e:
            assert "organization member" in str(e)
        else:
            raise AssertionError("re-keyed an organization member")
        db.refresh(member)
        assert member.role == "org_admin"

    def test_run_never_raises_on_bad_configuration(self, monkeypatch, capsys):
        monkeypatch.setenv("PLATFORM_ADMIN_EMAIL", "ops@nexadesk.example.com")
        monkeypatch.setenv("PLATFORM_ADMIN_PASSWORD", "weak")
        bootstrap.run()  # logs, does not stop the API from starting
        assert "not configured" in capsys.readouterr().err
