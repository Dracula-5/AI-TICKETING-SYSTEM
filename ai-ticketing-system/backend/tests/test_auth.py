"""
Tests for authentication endpoints: register, login, /auth/me.
"""

import pytest
from tests.conftest import auth_headers


class TestRegister:
    def test_register_success(self, client, tenant):
        resp = client.post("/auth/register", json={
            "name": "New User",
            "email": "newuser@test.com",
            "password": "secret123",
            "role": "customer",
            "tenant_id": tenant.id,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, client, customer_user, tenant):
        resp = client.post("/auth/register", json={
            "name": "Dup",
            "email": customer_user.email,
            "password": "any",
            "role": "customer",
            "tenant_id": tenant.id,
        })
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    def test_register_simple_creates_token(self, client, tenant):
        resp = client.post("/auth/register-simple", json={
            "email": "simple@test.com",
            "password": "pass123",
            "tenant_id": tenant.id,
        })
        assert resp.status_code == 201
        assert "access_token" in resp.json()


class TestLogin:
    def test_login_success(self, client, customer_user):
        resp = client.post(
            "/auth/login",
            data={"username": customer_user.email, "password": "customer123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, client, customer_user):
        resp = client.post(
            "/auth/login",
            data={"username": customer_user.email, "password": "wrongpass"},
        )
        assert resp.status_code == 401

    def test_login_unknown_email(self, client):
        resp = client.post(
            "/auth/login",
            data={"username": "ghost@test.com", "password": "any"},
        )
        assert resp.status_code == 401


class TestGetMe:
    def test_get_me_authenticated(self, client, customer_user):
        resp = client.get("/auth/me", headers=auth_headers(customer_user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == customer_user.email
        assert data["role"] == "customer"

    def test_get_me_unauthenticated(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401
