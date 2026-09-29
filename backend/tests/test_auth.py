from datetime import timedelta

from app.core.security import hash_token
from app.db.database import utcnow
from app.db.models import AuditLog, Category, EmailOutbox, RefreshToken, SlaPolicy, Team, Tenant, User, UserToken
from tests.conftest import PASSWORD, auth, make_org, make_user

REG = "/api/v1/auth/register"
STRONG = "Str0ng-Passw0rd"


def register(client, email="founder@newco.example.com", org="NewCo", **extra):
    body = {"name": "Nadia Founder", "email": email, "password": STRONG, "organization_name": org, **extra}
    return client.post(REG, json=body)


def login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", data={"username": email, "password": password})


def _raw_token_from_outbox(db, email, template):
    row = (
        db.query(EmailOutbox)
        .filter(EmailOutbox.to_email == email, EmailOutbox.template == template)
        .order_by(EmailOutbox.id.desc())
        .first()
    )
    return row.body_text.split("token=")[1].split()[0]


class TestRegistration:
    def test_creates_org_with_admin_and_default_configuration(self, client, db):
        resp = register(client)
        assert resp.status_code == 201, resp.text
        assert resp.json()["access_token"]
        assert "nexadesk_refresh" in resp.cookies

        user = db.query(User).filter(User.email == "founder@newco.example.com").one()
        assert user.role == "org_admin"
        tenant = db.get(Tenant, user.tenant_id)
        assert tenant.name == "NewCo" and tenant.slug == "newco" and not tenant.is_demo
        assert db.query(Team).filter(Team.tenant_id == tenant.id).count() >= 5
        assert db.query(Category).filter(Category.tenant_id == tenant.id).count() >= 8
        assert db.query(SlaPolicy).filter(SlaPolicy.tenant_id == tenant.id).count() == 4
        assert db.query(EmailOutbox).filter(EmailOutbox.template == "email_verification").count() == 1

    def test_caller_cannot_choose_role_or_tenant(self, client, db, org_a):
        # Regression for audit finding A1/A2: extra fields are ignored; the
        # caller always becomes admin of a *new* organization.
        resp = register(client, role="platform_admin", tenant_id=org_a.id)
        assert resp.status_code == 201
        user = db.query(User).filter(User.email == "founder@newco.example.com").one()
        assert user.role == "org_admin"
        assert user.tenant_id != org_a.id

    def test_duplicate_email_rejected(self, client):
        assert register(client).status_code == 201
        assert register(client, org="Other").status_code == 409

    def test_email_is_case_insensitive(self, client):
        assert register(client, email="Case@NewCo.example.com").status_code == 201
        assert register(client, email="case@newco.example.com", org="XY Co").status_code == 409

    def test_weak_password_rejected(self, client):
        resp = client.post(
            REG, json={"name": "A", "email": "a@x.example.com", "password": "short", "organization_name": "Org"}
        )
        assert resp.status_code == 422

    def test_must_choose_new_org_or_portal(self, client):
        resp = client.post(REG, json={"name": "A", "email": "a@x.example.com", "password": STRONG})
        assert resp.status_code == 422

    def test_slug_collision_gets_suffix(self, client, db):
        register(client, email="one@x.example.com", org="Same Name")
        register(client, email="two@x.example.com", org="Same Name")
        slugs = sorted(t.slug for t in db.query(Tenant).all())
        assert slugs[0] == "same-name" and slugs[1].startswith("same-name-")


class TestPortalSignup:
    def test_closed_portal_is_not_found(self, client, org_a):
        resp = client.post(
            REG, json={"name": "E", "email": "e@acme.example.com", "password": STRONG, "join_slug": org_a.slug}
        )
        assert resp.status_code == 404
        assert client.get(f"/api/v1/organizations/portal/{org_a.slug}").status_code == 404

    def test_open_portal_creates_customer(self, client, db, org_a):
        org_a.settings = {
            **org_a.settings,
            "portal_signup_enabled": True,
            "portal_allowed_domains": ["acme.example.com"],
        }
        db.commit()
        assert client.get(f"/api/v1/organizations/portal/{org_a.slug}").json()["name"] == "Acme Corp"

        resp = client.post(
            REG, json={"name": "Emp", "email": "emp@acme.example.com", "password": STRONG, "join_slug": org_a.slug}
        )
        assert resp.status_code == 201
        user = db.query(User).filter(User.email == "emp@acme.example.com").one()
        assert (user.role, user.tenant_id) == ("customer", org_a.id)

    def test_domain_restriction(self, client, db, org_a):
        org_a.settings = {
            **org_a.settings,
            "portal_signup_enabled": True,
            "portal_allowed_domains": ["acme.example.com"],
        }
        db.commit()
        resp = client.post(
            REG, json={"name": "X", "email": "x@elsewhere.example.com", "password": STRONG, "join_slug": org_a.slug}
        )
        assert resp.status_code == 403


class TestLogin:
    def test_success_records_last_login_and_audit(self, client, db, agent_a):
        resp = login(client, "AGENT@acme.example.com")
        assert resp.status_code == 200
        assert resp.json()["expires_in"] == 15 * 60
        db.refresh(agent_a)
        assert agent_a.last_login_at is not None
        assert (
            db.query(AuditLog).filter(AuditLog.action == "auth.login", AuditLog.actor_user_id == agent_a.id).count()
            == 1
        )

    def test_wrong_password_and_unknown_email_look_identical(self, client, db, agent_a):
        wrong = login(client, agent_a.email, "Nope-12345678")
        unknown = login(client, "ghost@acme.example.com", "Nope-12345678")
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()
        assert db.query(AuditLog).filter(AuditLog.action == "auth.login_failed").count() == 2

    def test_deactivated_user_cannot_login_or_use_token(self, client, db, agent_a):
        headers = auth(agent_a)
        agent_a.is_active = False
        db.commit()
        assert login(client, agent_a.email).status_code == 403
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401

    def test_invalid_token_rejected(self, client):
        assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_me_includes_org_and_permissions(self, client, agent_a):
        body = client.get("/api/v1/auth/me", headers=auth(agent_a)).json()
        assert body["organization"]["name"] == "Acme Corp"
        assert "tickets:work" in body["permissions"] and "org:update" not in body["permissions"]
        assert len(body["team_ids"]) == 2


class TestRefreshTokens:
    def test_refresh_rotates_the_cookie(self, client, agent_a):
        login(client, agent_a.email)
        first = client.cookies.get("nexadesk_refresh")
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200 and resp.json()["access_token"]
        assert client.cookies.get("nexadesk_refresh") != first

    def test_reusing_a_rotated_token_revokes_the_family(self, client, db, agent_a):
        login(client, agent_a.email)
        stolen = client.cookies.get("nexadesk_refresh")
        assert client.post("/api/v1/auth/refresh").status_code == 200

        client.cookies.clear()
        client.cookies.set("nexadesk_refresh", stolen, path="/api/v1/auth")
        assert client.post("/api/v1/auth/refresh").status_code == 401
        assert (
            db.query(RefreshToken).filter(RefreshToken.user_id == agent_a.id, RefreshToken.revoked_at.is_(None)).count()
            == 0
        )
        assert db.query(AuditLog).filter(AuditLog.action == "auth.refresh_token_reuse").count() == 1

    def test_logout_revokes_session(self, client, agent_a):
        login(client, agent_a.email)
        cookie = client.cookies.get("nexadesk_refresh")
        assert client.post("/api/v1/auth/logout").status_code == 200
        client.cookies.set("nexadesk_refresh", cookie, path="/api/v1/auth")
        assert client.post("/api/v1/auth/refresh").status_code == 401

    def test_no_cookie(self, client):
        assert client.post("/api/v1/auth/refresh").status_code == 401


class TestEmailVerification:
    def test_verify_with_emailed_token(self, client, db):
        register(client)
        raw = _raw_token_from_outbox(db, "founder@newco.example.com", "email_verification")
        assert client.post("/api/v1/auth/verify-email", json={"token": raw}).status_code == 200
        assert db.query(User).filter(User.email == "founder@newco.example.com").one().email_verified_at
        # single use
        assert client.post("/api/v1/auth/verify-email", json={"token": raw}).status_code == 400

    def test_tokens_are_stored_hashed(self, client, db):
        register(client)
        raw = _raw_token_from_outbox(db, "founder@newco.example.com", "email_verification")
        assert db.query(UserToken).filter(UserToken.token_hash == raw).count() == 0
        assert db.query(UserToken).filter(UserToken.token_hash == hash_token(raw)).count() == 1


class TestPasswordReset:
    def test_full_reset_flow_revokes_sessions(self, client, db, agent_a):
        login(client, agent_a.email)
        old_cookie = client.cookies.get("nexadesk_refresh")
        assert client.post("/api/v1/auth/forgot-password", json={"email": agent_a.email}).status_code == 202
        raw = _raw_token_from_outbox(db, agent_a.email, "password_reset")

        resp = client.post("/api/v1/auth/reset-password", json={"token": raw, "new_password": "Brand-New-Pass1"})
        assert resp.status_code == 200
        assert login(client, agent_a.email, "Brand-New-Pass1").status_code == 200
        assert login(client, agent_a.email).status_code == 401
        client.cookies.clear()
        client.cookies.set("nexadesk_refresh", old_cookie, path="/api/v1/auth")
        assert client.post("/api/v1/auth/refresh").status_code == 401

    def test_unknown_email_gives_same_response_and_sends_nothing(self, client, db):
        resp = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@acme.example.com"})
        assert resp.status_code == 202
        assert db.query(EmailOutbox).count() == 0

    def test_expired_token_rejected(self, client, db, agent_a):
        client.post("/api/v1/auth/forgot-password", json={"email": agent_a.email})
        raw = _raw_token_from_outbox(db, agent_a.email, "password_reset")
        db.query(UserToken).update({UserToken.expires_at: utcnow() - timedelta(minutes=1)})
        db.commit()
        resp = client.post("/api/v1/auth/reset-password", json={"token": raw, "new_password": "Brand-New-Pass1"})
        assert resp.status_code == 400

    def test_demo_org_accounts_cannot_be_reset(self, client, db):
        demo = make_org(db, "Demo Org", is_demo=True, data_origin="demo")
        user = make_user(db, demo, "org_admin", "admin@demo.example.com")
        client.post("/api/v1/auth/forgot-password", json={"email": user.email})
        assert db.query(EmailOutbox).count() == 0


class TestChangePassword:
    def test_change_requires_current_password(self, client, agent_a):
        bad = client.put(
            "/api/v1/users/me/password",
            json={"current_password": "wrong-Pass1", "new_password": "Another-Pass9"},
            headers=auth(agent_a),
        )
        assert bad.status_code == 400
        ok = client.put(
            "/api/v1/users/me/password",
            json={"current_password": PASSWORD, "new_password": "Another-Pass9"},
            headers=auth(agent_a),
        )
        assert ok.status_code == 200

    def test_blocked_in_demo_org(self, client, db):
        demo = make_org(db, "Demo Org", is_demo=True, data_origin="demo")
        user = make_user(db, demo, "agent", "agent@demo.example.com")
        resp = client.put(
            "/api/v1/users/me/password",
            json={"current_password": PASSWORD, "new_password": "Another-Pass9"},
            headers=auth(user),
        )
        assert resp.status_code == 403
