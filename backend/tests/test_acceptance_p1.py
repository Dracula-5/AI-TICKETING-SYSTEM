"""
P1 acceptance scenario, end to end, through public HTTP endpoints only
(the same calls the web UI makes). Each assertion block maps to one
acceptance criterion in docs/execution_plan.md §P1.

    Register org → invite agent → open requester portal → requester signs up →
    creates ticket → rules triage → agent takes & works it → waits on requester →
    requester replies → resolved → requester confirms → closed →
    admin sees analytics → every step is in the audit log.
"""

from fastapi.testclient import TestClient

from app.main import app

API = "/api/v1"
PW = "Accept4nce-Test"


def bearer(resp):
    assert resp.status_code in (200, 201), resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def outbox_link(client, email, marker):
    items = client.get(f"{API}/dev/outbox", params={"to": email}).json()
    body = next(i["body_text"] for i in items if marker in i["body_text"])
    return body.split("token=")[1].split()[0]


def test_p1_acceptance_workflow():
    # Separate clients = separate browsers (separate refresh cookies).
    with TestClient(app) as admin_c, TestClient(app) as agent_c, TestClient(app) as req_c:
        # 1. User can register; organization is created.
        admin = bearer(
            admin_c.post(
                f"{API}/auth/register",
                json={
                    "name": "Priya Admin",
                    "email": "priya@northwind.example.com",
                    "password": PW,
                    "organization_name": "Northwind Health",
                },
            )
        )
        me = admin_c.get(f"{API}/auth/me", headers=admin).json()
        assert me["role"] == "org_admin" and me["organization"]["name"] == "Northwind Health"
        slug = me["organization"]["slug"]

        # ...and can verify their email from the emailed link.
        token = outbox_link(admin_c, "priya@northwind.example.com", "verify-email")
        assert admin_c.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200

        # 2. Users can be invited (agent, into the Service Desk team).
        teams = {t["name"]: t["id"] for t in admin_c.get(f"{API}/teams", headers=admin).json()}
        inv = admin_c.post(
            f"{API}/organizations/me/invitations",
            headers=admin,
            json={"email": "sam@northwind.example.com", "role": "agent", "team_id": teams["Service Desk"]},
        ).json()
        invite_token = inv["invite_url"].split("token=")[1]
        preview = agent_c.get(f"{API}/auth/invitations/{invite_token}").json()
        assert preview["organization_name"] == "Northwind Health" and preview["role"] == "agent"
        agent = bearer(
            agent_c.post(
                f"{API}/auth/accept-invitation", json={"token": invite_token, "name": "Sam Agent", "password": PW}
            )
        )
        agent_id = agent_c.get(f"{API}/auth/me", headers=agent).json()["id"]

        # Admin opens the requester portal for the company domain.
        settings = admin_c.get(f"{API}/organizations/me", headers=admin).json()["settings"]
        admin_c.patch(
            f"{API}/organizations/me",
            headers=admin,
            json={
                "settings": {
                    **settings,
                    "portal_signup_enabled": True,
                    "portal_allowed_domains": ["northwind.example.com"],
                }
            },
        )

        # 3. Customer can create a ticket (after joining through the portal).
        requester = bearer(
            req_c.post(
                f"{API}/auth/register",
                json={
                    "name": "Rita Requester",
                    "email": "rita@northwind.example.com",
                    "password": PW,
                    "join_slug": slug,
                },
            )
        )
        ticket = req_c.post(
            f"{API}/tickets",
            headers=requester,
            json={
                "title": "Cannot log in to the payroll portal",
                "description": "Since this morning the payroll login says my password is wrong.",
            },
        ).json()
        tid = ticket["id"]
        assert ticket["status"] == "triaged" and ticket["category"] == "Access & Identity"
        assert ticket["team"]["name"] == "Service Desk" and ticket["sla"]["state"] == "ok"

        # 4. Agent can process the ticket.
        queue = agent_c.get(
            f"{API}/tickets", params={"assignee": "unassigned", "team_id": teams["Service Desk"]}, headers=agent
        ).json()
        assert [t["id"] for t in queue["items"]] == [tid]
        assert (
            agent_c.post(f"{API}/tickets/{tid}/assign", json={"assignee_id": agent_id}, headers=agent).status_code
            == 200
        )
        for step in ({"to_status": "acknowledged"}, {"to_status": "in_progress"}):
            assert agent_c.post(f"{API}/tickets/{tid}/transitions", json=step, headers=agent).status_code == 200
        agent_c.post(
            f"{API}/tickets/{tid}/comments",
            headers=agent,
            json={"content": "Account was locked after 5 failed attempts.", "visibility": "internal"},
        )
        agent_c.post(
            f"{API}/tickets/{tid}/transitions",
            headers=agent,
            json={"to_status": "waiting_for_customer", "reason": "Please confirm your employee ID."},
        )
        agent_c.post(
            f"{API}/tickets/{tid}/attachments",
            headers=agent,
            files={"file": ("steps.txt", b"1. Reset password\n2. Sign in", "text/plain")},
        )

        # Requester sees the question (not the internal note) and replies.
        visible = [c["content"] for c in req_c.get(f"{API}/tickets/{tid}/comments", headers=requester).json()]
        assert visible == ["Please confirm your employee ID."]
        history = req_c.get(f"{API}/tickets/{tid}/history", headers=requester).json()
        assert all(h["reason"] is None for h in history if h["to_status"] == "triaged")
        notes = req_c.get(f"{API}/notifications", headers=requester).json()
        assert any(n["type"] == "ticket_waiting" and "employee ID" in (n["message"] or "") for n in notes)
        req_c.post(f"{API}/tickets/{tid}/comments", json={"content": "Employee ID 40721"}, headers=requester)
        assert req_c.get(f"{API}/tickets/{tid}", headers=requester).json()["status"] == "in_progress"

        resolved = agent_c.post(
            f"{API}/tickets/{tid}/transitions",
            headers=agent,
            json={"to_status": "resolved", "resolution_summary": "Unlocked the account and reset the password."},
        ).json()
        assert resolved["status"] == "resolved"

        # 5. Customer can see the resolution and confirm it.
        seen = req_c.get(f"{API}/tickets/{tid}", headers=requester).json()
        assert seen["resolution_summary"] == "Unlocked the account and reset the password."
        assert "closed" in seen["allowed_transitions"]
        assert len(req_c.get(f"{API}/tickets/{tid}/attachments", headers=requester).json()) == 1
        closed = req_c.post(
            f"{API}/tickets/{tid}/confirm-resolution", json={"accepted": True}, headers=requester
        ).json()
        assert closed["status"] == "closed"

        # 6. Admin can view analytics.
        overview = admin_c.get(f"{API}/analytics/overview", headers=admin).json()
        assert overview["resolved_last_30d"] == 1 and overview["open_tickets"] == 0
        assert overview["sla_compliance_pct_30d"] == 100.0

        # 7. Every important action is in the audit log.
        actions = [
            e["action"]
            for e in admin_c.get(f"{API}/audit-logs", params={"page_size": 200}, headers=admin).json()["items"]
        ]
        for expected in (
            "org.create",
            "auth.register",
            "auth.email_verified",
            "user.invite",
            "user.invitation_accepted",
            "org.update",
            "ticket.create",
            "ticket.assign",
            "ticket.transition",
            "comment.create",
            "attachment.upload",
        ):
            assert expected in actions, expected
        history = [h["to_status"] for h in admin_c.get(f"{API}/tickets/{tid}/history", headers=admin).json()]
        assert history == [
            "submitted",
            "triaged",
            "assigned",
            "acknowledged",
            "in_progress",
            "waiting_for_customer",
            "in_progress",
            "resolved",
            "closed",
        ]
