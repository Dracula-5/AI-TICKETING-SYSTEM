"""
Tenant isolation: a user of organization B must not be able to read or change
anything that belongs to organization A — by listing, by guessing ids, or by
passing A's ids in request bodies. Foreign ids return 404 (not 403) so their
existence isn't confirmed.

Also covers intra-tenant isolation between requesters (audit finding A8/A9).
"""

import pytest

from app.db.models import Invitation, Notification
from tests.conftest import assign, auth, create_ticket, move, team_id

API = "/api/v1"


@pytest.fixture()
def world(client, db, org_a, admin_a, manager_a, agent_a, customer_a, org_b, admin_b, agent_b, customer_b):
    ticket = create_ticket(client, customer_a, title="Acme secret VPN issue", description="Internal hostnames inside")
    assign(client, manager_a, ticket["id"], agent_a.id)
    comment = client.post(
        f"{API}/tickets/{ticket['id']}/comments",
        json={"content": "note", "visibility": "internal"},
        headers=auth(agent_a),
    ).json()
    att = client.post(
        f"{API}/tickets/{ticket['id']}/attachments",
        headers=auth(customer_a),
        files={"file": ("log.txt", b"error 809", "text/plain")},
    ).json()
    inv = client.post(
        f"{API}/organizations/me/invitations",
        json={"email": "new@acme.example.com", "role": "agent"},
        headers=auth(admin_a),
    ).json()
    return {
        "ticket": ticket["id"],
        "comment": comment["id"],
        "attachment": att["id"],
        "invitation": inv["id"],
        "team": team_id(db, org_a, "Service Desk"),
        "category_id": None,
        "notification": db.query(Notification.id).filter(Notification.user_id == agent_a.id).first()[0],
    }


FOREIGN_READS = [
    "/tickets/{ticket}",
    "/tickets/{ticket}/history",
    "/tickets/{ticket}/comments",
    "/tickets/{ticket}/attachments",
    "/attachments/{attachment}/download",
]


@pytest.mark.parametrize("path", FOREIGN_READS)
@pytest.mark.parametrize("who", ["admin_b", "agent_b", "customer_b"])
def test_foreign_reads_are_not_found(client, world, request, path, who):
    user = request.getfixturevalue(who)
    resp = client.get(API + path.format(**world), headers=auth(user))
    assert resp.status_code == 404, (path, resp.status_code, resp.text)


FOREIGN_WRITES = [
    ("patch", "/tickets/{ticket}", {"title": "pwned"}),
    ("post", "/tickets/{ticket}/transitions", {"to_status": "closed", "reason": "x"}),
    ("post", "/tickets/{ticket}/assign", {"assignee_id": None}),
    ("post", "/tickets/{ticket}/comments", {"content": "hi"}),
    ("post", "/tickets/{ticket}/confirm-resolution", {"accepted": True}),
    ("patch", "/teams/{team}", {"name": "Hijacked"}),
    ("put", "/teams/{team}/members", {"user_ids": []}),
    ("delete", "/organizations/me/invitations/{invitation}", None),
    ("put", "/notifications/{notification}/read", None),
]


@pytest.mark.parametrize("method,path,body", FOREIGN_WRITES)
def test_foreign_writes_are_not_found(client, world, admin_b, method, path, body):
    kwargs = {"headers": auth(admin_b)}
    if body is not None:
        kwargs["json"] = body
    resp = getattr(client, method)(API + path.format(**world), **kwargs)
    assert resp.status_code == 404, (method, path, resp.status_code, resp.text)


def test_lists_only_contain_own_org(client, world, admin_b, agent_b, customer_b):
    create_ticket(client, customer_b, title="Globex printer", description="jam")
    for user in (admin_b, agent_b):
        items = client.get(f"{API}/tickets", headers=auth(user)).json()["items"]
        assert [t["title"] for t in items] == ["Globex printer"]
    members = client.get(f"{API}/organizations/me/members", headers=auth(admin_b)).json()["items"]
    assert all(m["email"].endswith("globex.example.com") for m in members)
    assert all(
        i["email"] != "new@acme.example.com"
        for i in client.get(f"{API}/organizations/me/invitations", headers=auth(admin_b)).json()
    )
    team_names = [t["id"] for t in client.get(f"{API}/teams", headers=auth(admin_b)).json()]
    assert world["team"] not in team_names
    overview = client.get(f"{API}/analytics/overview", headers=auth(admin_b)).json()
    assert overview["open_tickets"] == 1
    logs = client.get(f"{API}/audit-logs", headers=auth(admin_b)).json()["items"]
    assert all("Acme" not in str(log["changes"]) for log in logs)


def test_cannot_assign_foreign_team_or_user(client, world, db, org_b, manager_a, agent_b):
    foreign_team = team_id(db, org_b, "Security")
    r = client.post(
        f"{API}/tickets/{world['ticket']}/assign",
        json={"assignee_id": None, "team_id": foreign_team},
        headers=auth(manager_a),
    )
    assert r.status_code == 404
    assert assign(client, manager_a, world["ticket"], agent_b.id).status_code == 404


def test_cannot_put_foreign_users_in_own_team(client, db, org_b, admin_b, agent_a, world):
    own_team = team_id(db, org_b, "Service Desk")
    r = client.put(f"{API}/teams/{own_team}/members", json={"user_ids": [agent_a.id]}, headers=auth(admin_b))
    assert r.status_code == 422


def test_invitation_targets_only_inviters_org(client, db, admin_b, world):
    client.post(
        f"{API}/organizations/me/invitations",
        json={"email": "x@globex.example.com", "role": "agent"},
        headers=auth(admin_b),
    )
    inv = db.query(Invitation).filter(Invitation.email == "x@globex.example.com").one()
    assert inv.tenant_id == admin_b.tenant_id


class TestRequesterIsolationWithinOrg:
    def test_customer_cannot_see_another_customers_ticket(self, client, customer_a, customer_a2):
        tid = create_ticket(client, customer_a)["id"]
        assert client.get(f"{API}/tickets/{tid}", headers=auth(customer_a2)).status_code == 404
        assert client.get(f"{API}/tickets", headers=auth(customer_a2)).json()["total"] == 0

    def test_customer_cannot_change_another_customers_ticket(self, client, customer_a, customer_a2):
        tid = create_ticket(client, customer_a)["id"]
        assert move(client, customer_a2, tid, "closed", reason="x").status_code == 404
        r = client.post(f"{API}/tickets/{tid}/comments", json={"content": "x"}, headers=auth(customer_a2))
        assert r.status_code == 404

    def test_customer_cannot_see_internal_notes_or_their_files(self, client, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, tid, agent_a.id)
        note = client.post(
            f"{API}/tickets/{tid}/comments",
            json={"content": "customer seems confused", "visibility": "internal"},
            headers=auth(agent_a),
        ).json()
        att = client.post(
            f"{API}/tickets/{tid}/attachments",
            data={"comment_id": note["id"]},
            headers=auth(agent_a),
            files={"file": ("internal.txt", b"debug dump", "text/plain")},
        ).json()
        client.post(f"{API}/tickets/{tid}/comments", json={"content": "We are on it"}, headers=auth(agent_a))

        seen = client.get(f"{API}/tickets/{tid}/comments", headers=auth(customer_a)).json()
        assert [c["content"] for c in seen] == ["We are on it"]
        assert client.get(f"{API}/attachments/{att['id']}/download", headers=auth(customer_a)).status_code == 404
        assert client.get(f"{API}/tickets/{tid}/attachments", headers=auth(customer_a)).json() == []
        staff_view = client.get(f"{API}/tickets/{tid}/comments", headers=auth(agent_a)).json()
        assert len(staff_view) == 2

    def test_customer_cannot_post_internal_note(self, client, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        r = client.post(
            f"{API}/tickets/{tid}/comments", json={"content": "x", "visibility": "internal"}, headers=auth(customer_a)
        )
        assert r.status_code == 403
