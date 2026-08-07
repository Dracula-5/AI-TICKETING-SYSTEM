"""
Tests for vendor registration, profile management, and admin verification.
"""

import pytest

from tests.conftest import auth_headers


def _register_payload(tenant_id, **overrides):
    payload = {
        "name": "Shop Owner",
        "email": "owner@shop.com",
        "password": "secret123",
        "tenant_id": tenant_id,
        "shop_name": "Owner's Electronics",
        "phone_number": "+91-9000000000",
        "shop_address": "1 MG Road, Bengaluru",
        "category": "Electronics",
    }
    payload.update(overrides)
    return payload


class TestVendorRegister:
    def test_register_creates_vendor_and_user(self, client, tenant):
        resp = client.post("/vendors/register", json=_register_payload(tenant.id))
        assert resp.status_code == 201
        assert "access_token" in resp.json()

    def test_duplicate_email_rejected(self, client, tenant, vendor_user):
        resp = client.post("/vendors/register", json=_register_payload(
            tenant.id, email=vendor_user.email, category="Fashion",
        ))
        assert resp.status_code == 400

    def test_register_requires_category(self, client, tenant):
        payload = _register_payload(tenant.id)
        del payload["category"]
        resp = client.post("/vendors/register", json=payload)
        assert resp.status_code == 422

    def test_register_rejects_invalid_category(self, client, tenant):
        resp = client.post("/vendors/register", json=_register_payload(tenant.id, category="Toys"))
        assert resp.status_code == 422

    def test_register_creates_vendor_with_category(self, client, tenant):
        resp = client.post("/vendors/register", json=_register_payload(tenant.id, category="Books"))
        assert resp.status_code == 201
        token = resp.json()["access_token"]
        me = client.get("/vendors/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["category"] == "Books"

    def test_second_vendor_same_category_rejected(self, client, db, tenant):
        first = client.post("/vendors/register", json=_register_payload(
            tenant.id, email="first@shop.com", category="Sports",
        ))
        assert first.status_code == 201

        second = client.post("/vendors/register", json=_register_payload(
            tenant.id, email="second@shop.com", category="Sports",
        ))
        assert second.status_code == 400

        from app.db.models import User
        assert db.query(User).filter(User.email == "second@shop.com").first() is None

    def test_same_category_different_tenant_allowed(self, client, db, tenant):
        from app.db.models import Tenant
        other_tenant = Tenant(name="Other Org", domain="othervendors.example.com")
        db.add(other_tenant)
        db.commit()
        db.refresh(other_tenant)

        first = client.post("/vendors/register", json=_register_payload(
            tenant.id, email="a@shop.com", category="Grocery",
        ))
        second = client.post("/vendors/register", json=_register_payload(
            other_tenant.id, email="b@shop.com", category="Grocery",
        ))
        assert first.status_code == 201
        assert second.status_code == 201

    def test_category_uniqueness_enforced_at_db_level(self, db, tenant, vendor_user):
        from app.db.models import User, Vendor
        from app.core.security import get_password_hash
        from sqlalchemy.exc import IntegrityError

        other_user = User(name="Other", email="other-category@test.com",
                           hashed_password=get_password_hash("x"), role="vendor", tenant_id=tenant.id)
        db.add(other_user)
        db.flush()

        db.add(Vendor(user_id=vendor_user.id, tenant_id=tenant.id, shop_name="A",
                       phone_number="+91-1", shop_address="X", category="Fashion"))
        db.flush()

        # A SAVEPOINT (begin_nested) scopes the expected failure to itself,
        # leaving the outer connection-level transaction that conftest's
        # `db` fixture manages untouched -- a plain db.commit() here would
        # desync the fixture's own teardown rollback (SAWarning).
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(Vendor(user_id=other_user.id, tenant_id=tenant.id, shop_name="B",
                               phone_number="+91-2", shop_address="Y", category="Fashion"))
                db.flush()


class TestCategoryAvailability:
    def test_all_available_when_empty(self, client, tenant):
        resp = client.get(f"/vendors/categories?tenant_id={tenant.id}")
        assert resp.status_code == 200
        assert all(c["available"] for c in resp.json())

    def test_taken_after_registration(self, client, tenant):
        client.post("/vendors/register", json=_register_payload(tenant.id, category="Electronics"))
        resp = client.get(f"/vendors/categories?tenant_id={tenant.id}")
        rows = {c["category"]: c for c in resp.json()}
        assert rows["Electronics"]["available"] is False
        assert rows["Electronics"]["shop_name"] == "Owner's Electronics"
        assert rows["Books"]["available"] is True

    def test_tenant_scoped(self, client, db, tenant):
        from app.db.models import Tenant
        other_tenant = Tenant(name="Isolated Org", domain="isolated-vendors.example.com")
        db.add(other_tenant)
        db.commit()
        db.refresh(other_tenant)

        client.post("/vendors/register", json=_register_payload(tenant.id, category="Electronics"))
        resp = client.get(f"/vendors/categories?tenant_id={other_tenant.id}")
        rows = {c["category"]: c for c in resp.json()}
        assert rows["Electronics"]["available"] is True

    def test_callable_without_auth(self, client):
        resp = client.get("/vendors/categories")
        assert resp.status_code == 200


class TestVendorProfile:
    def test_vendor_can_view_own_profile(self, client, vendor_user, vendor):
        resp = client.get("/vendors/me", headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        assert resp.json()["shop_name"] == "Test Shop"

    def test_customer_cannot_view_vendor_me(self, client, customer_user):
        resp = client.get("/vendors/me", headers=auth_headers(customer_user))
        assert resp.status_code == 403

    def test_vendor_can_update_own_profile(self, client, vendor_user, vendor):
        resp = client.put("/vendors/me", json={"shop_name": "Renamed Shop"}, headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        assert resp.json()["shop_name"] == "Renamed Shop"

    def test_public_profile_hides_internal_fields(self, client, customer_user, vendor):
        resp = client.get(f"/vendors/{vendor.id}", headers=auth_headers(customer_user))
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" not in data
        assert "tenant_id" not in data
        assert data["shop_name"] == "Test Shop"


class TestVendorAdmin:
    def test_admin_can_list_vendors(self, client, admin_user, vendor):
        resp = client.get("/vendors/", headers=auth_headers(admin_user))
        assert resp.status_code == 200
        assert any(v["id"] == vendor.id for v in resp.json())

    def test_non_admin_cannot_list_vendors(self, client, vendor_user, vendor):
        resp = client.get("/vendors/", headers=auth_headers(vendor_user))
        assert resp.status_code == 403

    def test_admin_can_verify_vendor(self, client, admin_user, vendor):
        assert vendor.is_verified is False
        resp = client.put(f"/vendors/{vendor.id}/verify", headers=auth_headers(admin_user))
        assert resp.status_code == 200
        assert resp.json()["is_verified"] is True
