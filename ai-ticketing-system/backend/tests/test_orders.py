"""
Tests for order creation (negotiated + direct buy), stock handling, and
vendor order status transitions.
"""
from tests.conftest import auth_headers


class TestCreateOrder:
    def test_direct_buy(self, client, customer_user, product):
        resp = client.post("/orders/", json={"product_id": product.id, "quantity": 2}, headers=auth_headers(customer_user))
        assert resp.status_code == 201
        data = resp.json()
        assert data["unit_price"] == product.price
        assert data["total_price"] == product.price * 2
        assert data["status"] == "pending"

    def test_delivery_address_persisted(self, client, customer_user, product):
        resp = client.post("/orders/", json={
            "product_id": product.id, "quantity": 1, "delivery_address": "221B Baker Street, London",
        }, headers=auth_headers(customer_user))
        assert resp.status_code == 201
        assert resp.json()["delivery_address"] == "221B Baker Street, London"

    def test_delivery_address_optional(self, client, customer_user, product):
        resp = client.post("/orders/", json={"product_id": product.id, "quantity": 1}, headers=auth_headers(customer_user))
        assert resp.status_code == 201
        assert resp.json()["delivery_address"] is None

    def test_stock_decrements(self, client, db, customer_user, product):
        initial_stock = product.stock_quantity
        client.post("/orders/", json={"product_id": product.id, "quantity": 3}, headers=auth_headers(customer_user))
        db.refresh(product)
        assert product.stock_quantity == initial_stock - 3

    def test_insufficient_stock_rejected(self, client, customer_user, product):
        resp = client.post("/orders/", json={"product_id": product.id, "quantity": 9999}, headers=auth_headers(customer_user))
        assert resp.status_code == 400

    def test_vendor_cannot_create_order(self, client, vendor_user, product):
        resp = client.post("/orders/", json={"product_id": product.id, "quantity": 1}, headers=auth_headers(vendor_user))
        assert resp.status_code == 403

    def test_order_from_accepted_negotiation(self, client, customer_user, vendor_user, product):
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user)).json()
        client.post(f"/negotiations/{created['id']}/accept", headers=auth_headers(vendor_user))

        resp = client.post(
            "/orders/",
            json={"product_id": product.id, "quantity": 1, "negotiation_session_id": created["id"]},
            headers=auth_headers(customer_user),
        )
        assert resp.status_code == 201
        assert resp.json()["unit_price"] == 800.0
        assert resp.json()["negotiation_session_id"] == created["id"]

    def test_order_from_open_negotiation_rejected(self, client, customer_user, product):
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user)).json()
        resp = client.post(
            "/orders/",
            json={"product_id": product.id, "quantity": 1, "negotiation_session_id": created["id"]},
            headers=auth_headers(customer_user),
        )
        assert resp.status_code == 400

    def test_cannot_use_other_customers_negotiation(self, client, db, tenant, customer_user, vendor_user, product):
        from app.db.models import User
        from app.core.security import get_password_hash
        other = User(name="Other Cust", email="other-order@test.com", hashed_password=get_password_hash("x"),
                     role="customer", tenant_id=tenant.id)
        db.add(other)
        db.commit()
        db.refresh(other)

        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user)).json()
        client.post(f"/negotiations/{created['id']}/accept", headers=auth_headers(vendor_user))

        resp = client.post(
            "/orders/",
            json={"product_id": product.id, "quantity": 1, "negotiation_session_id": created["id"]},
            headers=auth_headers(other),
        )
        assert resp.status_code == 403


class TestOrderListing:
    def test_customer_sees_own_orders(self, client, customer_user, product):
        client.post("/orders/", json={"product_id": product.id, "quantity": 1}, headers=auth_headers(customer_user))
        resp = client.get("/orders/my", headers=auth_headers(customer_user))
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_vendor_sees_received_orders(self, client, customer_user, vendor_user, product):
        client.post("/orders/", json={"product_id": product.id, "quantity": 1}, headers=auth_headers(customer_user))
        resp = client.get("/orders/vendor/received", headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestOrderStatus:
    def test_vendor_can_update_status(self, client, customer_user, vendor_user, product):
        order = client.post("/orders/", json={"product_id": product.id, "quantity": 1}, headers=auth_headers(customer_user)).json()
        resp = client.put(f"/orders/{order['id']}/status?new_status=confirmed", headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    def test_customer_cannot_update_status(self, client, customer_user, product):
        order = client.post("/orders/", json={"product_id": product.id, "quantity": 1}, headers=auth_headers(customer_user)).json()
        resp = client.put(f"/orders/{order['id']}/status?new_status=confirmed", headers=auth_headers(customer_user))
        assert resp.status_code == 403

    def test_invalid_status_rejected(self, client, customer_user, vendor_user, product):
        order = client.post("/orders/", json={"product_id": product.id, "quantity": 1}, headers=auth_headers(customer_user)).json()
        resp = client.put(f"/orders/{order['id']}/status?new_status=bogus", headers=auth_headers(vendor_user))
        assert resp.status_code == 400

    def test_other_vendor_cannot_update(self, client, db, tenant, customer_user, product):
        from app.db.models import User, Vendor
        from app.core.security import get_password_hash
        other_user = User(name="Other Vendor", email="other-vendor-ord@test.com", hashed_password=get_password_hash("x"),
                           role="vendor", tenant_id=tenant.id)
        db.add(other_user)
        db.commit()
        db.refresh(other_user)
        other_vendor = Vendor(user_id=other_user.id, tenant_id=tenant.id, shop_name="Other",
                               phone_number="+91-3", shop_address="Elsewhere")
        db.add(other_vendor)
        db.commit()

        order = client.post("/orders/", json={"product_id": product.id, "quantity": 1}, headers=auth_headers(customer_user)).json()
        resp = client.put(f"/orders/{order['id']}/status?new_status=confirmed", headers=auth_headers(other_user))
        assert resp.status_code == 403
