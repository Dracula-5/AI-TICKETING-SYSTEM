"""Role-based access: each role can do what its job needs and nothing more."""

import pytest

from app.core.rbac import ROLE_PERMISSIONS, P, Role
from tests.conftest import auth, create_ticket, make_user

API = "/api/v1"


def test_every_role_has_a_permission_set():
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_permission_ladder():
    agent, manager, admin = (ROLE_PERMISSIONS[r] for r in (Role.AGENT, Role.MANAGER, Role.ORG_ADMIN))
    assert agent < manager < admin
    assert P.PLATFORM_ADMIN not in admin
    assert ROLE_PERMISSIONS[Role.PLATFORM_ADMIN] == frozenset({P.PLATFORM_ADMIN})
    # Analysts read everything operational but change nothing.
    analyst = ROLE_PERMISSIONS[Role.ANALYST]
    assert {P.TICKETS_READ_ALL, P.ANALYTICS_READ, P.AUDIT_READ} <= analyst
    assert not analyst & {P.TICKETS_CREATE, P.TICKETS_WORK, P.TICKETS_ASSIGN, P.USERS_INVITE, P.ORG_UPDATE}


# (method, path, body, roles allowed) — every other role must get 403.
MATRIX = [
    ("get", "/analytics/overview", None, {"org_admin", "manager", "analyst"}),
    ("get", "/audit-logs", None, {"org_admin", "manager", "analyst"}),
    ("get", "/organizations/me/members", None, {"org_admin", "manager", "agent", "analyst"}),
    ("get", "/organizations/me/invitations", None, {"org_admin", "manager"}),
    ("patch", "/organizations/me", {"name": "Renamed Org"}, {"org_admin"}),
    ("post", "/teams", {"name": "New Team"}, {"org_admin"}),
    ("get", "/teams", None, {"org_admin", "manager", "agent", "analyst"}),
    (
        "put",
        "/sla-policies",
        {"policies": [{"priority": "low", "first_response_minutes": 60, "resolution_minutes": 600}]},
        {"org_admin"},
    ),
    ("post", "/categories", {"name": "Brand New"}, {"org_admin"}),
    ("post", "/tickets", {"title": "Role test", "description": "x"}, {"org_admin", "manager", "agent", "customer"}),
    ("get", "/platform/overview", None, set()),
]
ORG_ROLES = ["org_admin", "manager", "agent", "customer", "analyst"]


@pytest.mark.parametrize("method,path,body,allowed", MATRIX)
@pytest.mark.parametrize("role", ORG_ROLES)
def test_endpoint_permissions(client, db, org_a, role, method, path, body, allowed):
    user = make_user(db, org_a, role, f"{role}@acme.example.com")
    kwargs = {"headers": auth(user)}
    if body is not None:
        kwargs["json"] = body
    resp = getattr(client, method)(API + path, **kwargs)
    if role in allowed:
        assert resp.status_code in (200, 201), (role, path, resp.status_code, resp.text)
    else:
        assert resp.status_code == 403, (role, path, resp.status_code, resp.text)


def test_manager_cannot_invite_admins(client, manager_a):
    r = client.post(
        f"{API}/organizations/me/invitations",
        json={"email": "boss@acme.example.com", "role": "org_admin"},
        headers=auth(manager_a),
    )
    assert r.status_code == 403
    r = client.post(
        f"{API}/organizations/me/invitations",
        json={"email": "agent9@acme.example.com", "role": "agent"},
        headers=auth(manager_a),
    )
    assert r.status_code == 201


def test_platform_admin_is_not_an_org_member(client, platform_admin):
    assert client.get(f"{API}/platform/overview", headers=auth(platform_admin)).status_code == 200
    assert client.get(f"{API}/tickets", headers=auth(platform_admin)).status_code == 403
    assert client.get(f"{API}/organizations/me", headers=auth(platform_admin)).status_code == 403


def test_analyst_is_read_only_on_tickets(client, customer_a, analyst_a):
    tid = create_ticket(client, customer_a)["id"]
    assert client.get(f"{API}/tickets/{tid}", headers=auth(analyst_a)).status_code == 200
    assert (
        client.post(f"{API}/tickets/{tid}/comments", json={"content": "x"}, headers=auth(analyst_a)).status_code == 403
    )
    assert (
        client.post(
            f"{API}/tickets/{tid}/transitions", json={"to_status": "escalated", "reason": "x"}, headers=auth(analyst_a)
        ).status_code
        == 403
    )
    assert client.patch(f"{API}/tickets/{tid}", json={"priority": "high"}, headers=auth(analyst_a)).status_code == 403


class TestMemberManagement:
    def test_admin_changes_role_and_deactivates(self, client, admin_a, agent_a):
        r = client.patch(
            f"{API}/organizations/me/members/{agent_a.id}", json={"role": "manager"}, headers=auth(admin_a)
        )
        assert r.status_code == 200 and r.json()["role"] == "manager"
        r = client.patch(
            f"{API}/organizations/me/members/{agent_a.id}", json={"is_active": False}, headers=auth(admin_a)
        )
        assert r.status_code == 200 and r.json()["is_active"] is False
        assert client.get(f"{API}/auth/me", headers=auth(agent_a)).status_code == 401

    def test_cannot_grant_platform_admin(self, client, admin_a, agent_a):
        r = client.patch(
            f"{API}/organizations/me/members/{agent_a.id}", json={"role": "platform_admin"}, headers=auth(admin_a)
        )
        assert r.status_code == 422

    def test_cannot_modify_self(self, client, admin_a):
        r = client.patch(f"{API}/organizations/me/members/{admin_a.id}", json={"role": "agent"}, headers=auth(admin_a))
        assert r.status_code == 409

    def test_admins_can_manage_other_admins_but_agents_cannot(self, client, db, org_a, admin_a):
        second = make_user(db, org_a, "org_admin", "admin2@acme.example.com")
        assert (
            client.patch(
                f"{API}/organizations/me/members/{second.id}", json={"role": "agent"}, headers=auth(admin_a)
            ).status_code
            == 200
        )
        db.refresh(second)
        assert (
            client.patch(
                f"{API}/organizations/me/members/{admin_a.id}", json={"role": "agent"}, headers=auth(second)
            ).status_code
            == 403
        )
