"""
Tests for the vendor/admin analytics endpoints and the admin product
moderation listing (GET /products/admin/all).
"""
from tests.conftest import auth_headers


class TestVendorAnalytics:
    def test_zero_state(self, client, vendor_user, vendor):
        resp = client.get("/analytics/vendor", headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_products"] == 0
        assert data["total_orders"] == 0
        assert data["total_revenue"] == 0.0
        assert data["negotiation_success_rate_pct"] == 0.0
        assert data["top_products"] == []

    def test_aggregates_after_activity(self, client, customer_user, vendor_user, vendor, product):
        # bump views
        client.get(f"/products/{product.id}", headers=auth_headers(customer_user))
        client.get(f"/products/{product.id}", headers=auth_headers(customer_user))

        # accepted negotiation -> order
        created = client.post(
            "/negotiations/", json={"product_id": product.id, "amount": 800.0},
            headers=auth_headers(customer_user),
        ).json()
        client.post(f"/negotiations/{created['id']}/accept", headers=auth_headers(vendor_user))
        order = client.post(
            "/orders/",
            json={"product_id": product.id, "quantity": 1, "negotiation_session_id": created["id"]},
            headers=auth_headers(customer_user),
        ).json()

        resp = client.get("/analytics/vendor", headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_products"] == 1
        assert data["total_views"] == 2
        assert data["total_orders"] == 1
        assert data["total_revenue"] == order["total_price"]
        assert data["total_negotiations"] == 1
        assert data["accepted_negotiations"] == 1
        assert data["negotiation_success_rate_pct"] == 100.0
        assert len(data["top_products"]) == 1
        assert data["top_products"][0]["id"] == product.id

    def test_role_gated(self, client, customer_user, admin_user):
        assert client.get("/analytics/vendor", headers=auth_headers(customer_user)).status_code == 403
        assert client.get("/analytics/vendor", headers=auth_headers(admin_user)).status_code == 403


class TestAdminAnalytics:
    def test_aggregates(self, client, admin_user, customer_user, vendor_user, vendor, product):
        client.post("/orders/", json={"product_id": product.id, "quantity": 1}, headers=auth_headers(customer_user))

        resp = client.get("/analytics/admin", headers=auth_headers(admin_user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_vendors"] >= 1
        assert data["total_products"] >= 1
        assert data["total_orders"] >= 1
        assert any(v["id"] == vendor.id for v in data["top_vendors"])

    def test_role_gated(self, client, customer_user, vendor_user):
        assert client.get("/analytics/admin", headers=auth_headers(customer_user)).status_code == 403
        assert client.get("/analytics/admin", headers=auth_headers(vendor_user)).status_code == 403


class TestAdminProductModeration:
    def test_lists_all_statuses(self, client, admin_user, vendor_user, product):
        client.put(f"/products/{product.id}/status?new_status=inactive", headers=auth_headers(admin_user))

        # public listing excludes inactive products
        public = client.get("/products/", headers=auth_headers(vendor_user)).json()
        assert not any(p["id"] == product.id for p in public["items"])

        # admin moderation listing includes it
        resp = client.get("/products/admin/all", headers=auth_headers(admin_user))
        assert resp.status_code == 200
        data = resp.json()
        assert any(p["id"] == product.id for p in data["items"])

    def test_status_filter(self, client, admin_user, product):
        client.put(f"/products/{product.id}/status?new_status=inactive", headers=auth_headers(admin_user))

        resp = client.get("/products/admin/all?status=inactive", headers=auth_headers(admin_user))
        assert resp.status_code == 200
        assert all(p["status"] == "inactive" for p in resp.json()["items"])

    def test_invalid_status_filter_rejected(self, client, admin_user):
        resp = client.get("/products/admin/all?status=bogus", headers=auth_headers(admin_user))
        assert resp.status_code == 400

    def test_role_gated(self, client, vendor_user, customer_user):
        assert client.get("/products/admin/all", headers=auth_headers(vendor_user)).status_code == 403
        assert client.get("/products/admin/all", headers=auth_headers(customer_user)).status_code == 403
