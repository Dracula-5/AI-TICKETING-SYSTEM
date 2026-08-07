"""
Tests for product CRUD, marketplace listing/search/filter/pagination,
tenant isolation, and role-gating.
"""

from tests.conftest import auth_headers


def _create_product(client, vendor_user, **overrides):
    payload = {
        "title": "Wireless Headphones",
        "description": "Noise-cancelling over-ear headphones",
        "price": 2999.0,
        "stock_quantity": 10,
        "image_urls": ["https://picsum.photos/seed/test/400/300"],
    }
    payload.update(overrides)
    return client.post("/products/", json=payload, headers=auth_headers(vendor_user))


class TestCreateProduct:
    def test_vendor_can_create_product(self, client, vendor_user, vendor):
        resp = _create_product(client, vendor_user)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Wireless Headphones"
        assert data["vendor"]["shop_name"] == "Test Shop"
        assert len(data["images"]) == 1

    def test_customer_cannot_create_product(self, client, customer_user):
        resp = _create_product(client, customer_user)
        assert resp.status_code == 403

    def test_created_product_inherits_vendor_category(self, client, vendor_user, vendor):
        resp = _create_product(client, vendor_user, category="Something-Bogus")
        assert resp.status_code == 201
        assert resp.json()["category"] == vendor.category == "Electronics"

    def test_vendor_without_profile_gets_404(self, client, db, tenant):
        from app.db.models import User
        from app.core.security import get_password_hash

        u = User(name="No Shop", email="noshop@test.com",
                 hashed_password=get_password_hash("x"), role="vendor", tenant_id=tenant.id)
        db.add(u)
        db.commit()
        db.refresh(u)
        resp = _create_product(client, u)
        assert resp.status_code == 404


class TestListProducts:
    def test_marketplace_lists_active_products(self, client, vendor_user, vendor, customer_user):
        _create_product(client, vendor_user)
        resp = client.get("/products/", headers=auth_headers(customer_user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["items"][0]["status"] == "active"

    def test_search_by_title(self, client, vendor_user, vendor, customer_user):
        _create_product(client, vendor_user, title="Bluetooth Speaker")
        _create_product(client, vendor_user, title="Cotton T-Shirt")
        resp = client.get("/products/?search=Speaker", headers=auth_headers(customer_user))
        assert resp.status_code == 200
        titles = [p["title"] for p in resp.json()["items"]]
        assert all("Speaker" in t for t in titles)

    def test_filter_by_price_range(self, client, vendor_user, vendor, customer_user):
        _create_product(client, vendor_user, title="Cheap Item", price=100.0)
        _create_product(client, vendor_user, title="Expensive Item", price=9000.0)
        resp = client.get("/products/?min_price=5000&max_price=10000", headers=auth_headers(customer_user))
        assert resp.status_code == 200
        for p in resp.json()["items"]:
            assert 5000 <= p["price"] <= 10000

    def test_pagination(self, client, vendor_user, vendor, customer_user):
        for i in range(5):
            _create_product(client, vendor_user, title=f"Item {i}")
        resp = client.get("/products/?page=1&page_size=2", headers=auth_headers(customer_user))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2

    def test_get_product_increments_views(self, client, vendor_user, vendor, customer_user):
        created = _create_product(client, vendor_user).json()
        first = client.get(f"/products/{created['id']}", headers=auth_headers(customer_user)).json()
        second = client.get(f"/products/{created['id']}", headers=auth_headers(customer_user)).json()
        assert second["views_count"] == first["views_count"] + 1

    def test_cross_tenant_product_not_found(self, client, db, vendor_user, vendor, customer_user):
        from app.db.models import Tenant, User, Vendor
        from app.core.security import get_password_hash

        other_tenant = Tenant(name="Other Org", domain="other.example.com")
        db.add(other_tenant)
        db.commit()
        db.refresh(other_tenant)

        other_vendor_user = User(
            name="Other Vendor", email="othervendor@test.com",
            hashed_password=get_password_hash("x"), role="vendor", tenant_id=other_tenant.id,
        )
        db.add(other_vendor_user)
        db.commit()
        db.refresh(other_vendor_user)

        other_vendor = Vendor(
            user_id=other_vendor_user.id, tenant_id=other_tenant.id,
            shop_name="Other Shop", phone_number="+91-1", shop_address="Elsewhere",
        )
        db.add(other_vendor)
        db.commit()
        db.refresh(other_vendor)

        created = _create_product(client, other_vendor_user).json()
        resp = client.get(f"/products/{created['id']}", headers=auth_headers(customer_user))
        assert resp.status_code == 404


class TestProductOwnership:
    def test_vendor_can_update_own_product(self, client, vendor_user, vendor):
        created = _create_product(client, vendor_user).json()
        resp = client.put(f"/products/{created['id']}", json={"price": 3499.0}, headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        assert resp.json()["price"] == 3499.0

    def test_update_cannot_change_category(self, client, vendor_user, vendor):
        created = _create_product(client, vendor_user).json()
        resp = client.put(f"/products/{created['id']}", json={"category": "Books"}, headers=auth_headers(vendor_user))
        # Pydantic v2 silently ignores unknown request fields (no `category`
        # on ProductUpdate anymore) -- this is a 200 no-op, not a 422.
        assert resp.status_code == 200
        assert resp.json()["category"] == "Electronics"

    def test_other_vendor_cannot_update_product(self, client, db, tenant, vendor_user, vendor):
        from app.db.models import User, Vendor
        from app.core.security import get_password_hash

        created = _create_product(client, vendor_user).json()

        other_user = User(name="Other", email="other@test.com",
                           hashed_password=get_password_hash("x"), role="vendor", tenant_id=tenant.id)
        db.add(other_user)
        db.commit()
        db.refresh(other_user)
        other_vendor = Vendor(user_id=other_user.id, tenant_id=tenant.id,
                               shop_name="Other Shop", phone_number="+91-2", shop_address="Nowhere")
        db.add(other_vendor)
        db.commit()

        resp = client.put(f"/products/{created['id']}", json={"price": 1.0}, headers=auth_headers(other_user))
        assert resp.status_code == 403

    def test_vendor_can_delete_own_product(self, client, vendor_user, vendor):
        created = _create_product(client, vendor_user).json()
        resp = client.delete(f"/products/{created['id']}", headers=auth_headers(vendor_user))
        assert resp.status_code == 204


class TestAdminModeration:
    def test_admin_can_change_product_status(self, client, admin_user, vendor_user, vendor):
        created = _create_product(client, vendor_user).json()
        resp = client.put(
            f"/products/{created['id']}/status?new_status=inactive",
            headers=auth_headers(admin_user),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "inactive"

    def test_vendor_cannot_change_product_status(self, client, vendor_user, vendor):
        created = _create_product(client, vendor_user).json()
        resp = client.put(
            f"/products/{created['id']}/status?new_status=inactive",
            headers=auth_headers(vendor_user),
        )
        assert resp.status_code == 403

    def test_invalid_status_rejected(self, client, admin_user, vendor_user, vendor):
        created = _create_product(client, vendor_user).json()
        resp = client.put(
            f"/products/{created['id']}/status?new_status=bogus",
            headers=auth_headers(admin_user),
        )
        assert resp.status_code == 400
