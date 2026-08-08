"""
Tests for self-service profile editing and password change (Settings page).
"""
from tests.conftest import auth_headers


class TestUpdateProfile:
    def test_update_name(self, client, customer_user):
        resp = client.put("/users/me", json={"name": "New Name"}, headers=auth_headers(customer_user))
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_update_email(self, client, customer_user):
        resp = client.put("/users/me", json={"email": "newmail@test.com"}, headers=auth_headers(customer_user))
        assert resp.status_code == 200
        assert resp.json()["email"] == "newmail@test.com"

    def test_duplicate_email_rejected(self, client, customer_user, vendor_user):
        resp = client.put("/users/me", json={"email": vendor_user.email}, headers=auth_headers(customer_user))
        assert resp.status_code == 400

    def test_keeping_own_email_is_not_a_conflict(self, client, customer_user):
        resp = client.put("/users/me", json={"email": customer_user.email, "name": "Same Email"}, headers=auth_headers(customer_user))
        assert resp.status_code == 200

    def test_role_and_tenant_not_editable(self, client, customer_user, tenant):
        resp = client.put("/users/me", json={"role": "admin", "tenant_id": 9999}, headers=auth_headers(customer_user))
        assert resp.status_code == 200
        assert resp.json()["role"] == "customer"
        assert resp.json()["tenant_id"] == tenant.id

    def test_unauthenticated_rejected(self, client):
        resp = client.put("/users/me", json={"name": "Nope"})
        assert resp.status_code == 401


class TestChangePassword:
    def test_change_password_success(self, client, customer_user):
        resp = client.put("/users/me/password", json={
            "current_password": "customer123", "new_password": "newpass456",
        }, headers=auth_headers(customer_user))
        assert resp.status_code == 200

        old_login = client.post("/auth/login", data={"username": customer_user.email, "password": "customer123"})
        assert old_login.status_code == 401

        new_login = client.post("/auth/login", data={"username": customer_user.email, "password": "newpass456"})
        assert new_login.status_code == 200

    def test_wrong_current_password_rejected(self, client, customer_user):
        resp = client.put("/users/me/password", json={
            "current_password": "wrong-password", "new_password": "whatever123",
        }, headers=auth_headers(customer_user))
        assert resp.status_code == 400

    def test_new_password_too_short_rejected(self, client, customer_user):
        resp = client.put("/users/me/password", json={
            "current_password": "customer123", "new_password": "abc",
        }, headers=auth_headers(customer_user))
        assert resp.status_code == 422
