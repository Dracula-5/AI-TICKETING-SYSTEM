"""
Tests for ticket lifecycle: creation, retrieval, status updates, and RBAC.
"""

import pytest
from tests.conftest import auth_headers


def _create_ticket(client, user, tenant_id, title="Test ticket", description="Something broke"):
    return client.post("/tickets/", json={
        "title": title,
        "description": description,
        "tenant_id": tenant_id,
    }, headers=auth_headers(user))


class TestCreateTicket:
    def test_customer_can_create(self, client, customer_user, tenant):
        resp = _create_ticket(client, customer_user, tenant.id)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test ticket"
        assert data["status"] == "open"
        assert data["tenant_id"] == tenant.id

    def test_ai_assigns_priority_automatically(self, client, customer_user, tenant):
        resp = _create_ticket(client, customer_user, tenant.id,
                              description="Server is down and database crashed urgently")
        assert resp.status_code == 201
        assert resp.json()["priority"] in ("critical", "high", "medium", "low")

    def test_ai_assigns_category_automatically(self, client, customer_user, tenant):
        resp = _create_ticket(client, customer_user, tenant.id,
                              title="WiFi outage", description="Network is not working")
        assert resp.status_code == 201
        assert resp.json()["category"] == "IT Support"

    def test_sla_due_is_populated(self, client, customer_user, tenant):
        resp = _create_ticket(client, customer_user, tenant.id)
        assert resp.status_code == 201
        assert resp.json()["sla_due"] is not None

    def test_tenant_mismatch_rejected(self, client, customer_user):
        resp = client.post("/tickets/", json={
            "title": "Cross-tenant hack",
            "description": "Should fail",
            "tenant_id": 9999,
        }, headers=auth_headers(customer_user))
        assert resp.status_code == 403

    def test_unauthenticated_cannot_create(self, client, tenant):
        resp = client.post("/tickets/", json={
            "title": "No auth",
            "description": "Should fail",
            "tenant_id": tenant.id,
        })
        assert resp.status_code == 401


class TestListTickets:
    def test_admin_sees_all_tenant_tickets(self, client, admin_user, customer_user, tenant):
        _create_ticket(client, customer_user, tenant.id, title="T1")
        _create_ticket(client, customer_user, tenant.id, title="T2")
        resp = client.get("/tickets/", headers=auth_headers(admin_user))
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_customer_sees_only_own_tickets(self, client, customer_user, admin_user, tenant):
        _create_ticket(client, customer_user, tenant.id, title="Mine")
        resp = client.get("/tickets/", headers=auth_headers(customer_user))
        assert resp.status_code == 200
        for ticket in resp.json():
            assert ticket["created_by_user_id"] == customer_user.id


class TestGetTicket:
    def test_get_existing_ticket(self, client, customer_user, tenant):
        create_resp = _create_ticket(client, customer_user, tenant.id)
        ticket_id = create_resp.json()["id"]
        resp = client.get(f"/tickets/{ticket_id}", headers=auth_headers(customer_user))
        assert resp.status_code == 200
        assert resp.json()["id"] == ticket_id

    def test_get_nonexistent_ticket_returns_404(self, client, customer_user):
        resp = client.get("/tickets/99999", headers=auth_headers(customer_user))
        assert resp.status_code == 404


class TestAdminAssign:
    def test_admin_can_assign_to_provider(self, client, admin_user, customer_user, provider_user, tenant):
        create_resp = _create_ticket(client, customer_user, tenant.id)
        ticket_id = create_resp.json()["id"]
        resp = client.put(
            f"/tickets/{ticket_id}/assign/{provider_user.id}",
            headers=auth_headers(admin_user),
        )
        assert resp.status_code == 200
        assert resp.json()["ticket"]["assigned_to_user_id"] == provider_user.id

    def test_customer_cannot_assign(self, client, customer_user, provider_user, tenant):
        create_resp = _create_ticket(client, customer_user, tenant.id)
        ticket_id = create_resp.json()["id"]
        resp = client.put(
            f"/tickets/{ticket_id}/assign/{provider_user.id}",
            headers=auth_headers(customer_user),
        )
        assert resp.status_code == 403


class TestSLACheck:
    def test_admin_can_trigger_sla_check(self, client, admin_user):
        resp = client.post("/tickets/admin/run-sla-check", headers=auth_headers(admin_user))
        assert resp.status_code == 200
        assert "tickets_escalated" in resp.json()

    def test_customer_cannot_trigger_sla_check(self, client, customer_user):
        resp = client.post("/tickets/admin/run-sla-check", headers=auth_headers(customer_user))
        assert resp.status_code == 403
