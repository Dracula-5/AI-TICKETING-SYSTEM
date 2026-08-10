"""
Tests for the negotiation REST endpoints and the WebSocket chat round trip.
There is no auto-negotiate AI engine anymore -- every message in a
negotiation comes from a real customer or vendor.
"""
import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token
from tests.conftest import auth_headers


class TestNegotiationREST:
    def test_customer_can_start_negotiation(self, client, customer_user, product):
        resp = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0, "message": "Can you do 800?"},
                            headers=auth_headers(customer_user))
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "open"
        assert len(data["messages"]) == 1
        assert data["messages"][0]["sender_role"] == "customer"

    def test_vendor_cannot_start_negotiation(self, client, vendor_user, product):
        resp = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(vendor_user))
        assert resp.status_code == 403

    def test_get_negotiation_participant_allowed(self, client, customer_user, product):
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user)).json()
        resp = client.get(f"/negotiations/{created['id']}", headers=auth_headers(customer_user))
        assert resp.status_code == 200

    def test_get_negotiation_non_participant_forbidden(self, client, db, tenant, customer_user, product):
        from app.db.models import User
        from app.core.security import get_password_hash
        other = User(name="Other", email="other-cust@test.com", hashed_password=get_password_hash("x"),
                     role="customer", tenant_id=tenant.id)
        db.add(other)
        db.commit()
        db.refresh(other)
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user)).json()
        resp = client.get(f"/negotiations/{created['id']}", headers=auth_headers(other))
        assert resp.status_code == 403

    def test_vendor_can_see_inbox(self, client, customer_user, vendor_user, product):
        client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user))
        resp = client.get("/negotiations/vendor/inbox", headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_accept_via_rest(self, client, customer_user, vendor_user, product):
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user)).json()
        resp = client.post(f"/negotiations/{created['id']}/accept", headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        assert resp.json()["current_offer_price"] == 800.0

    def test_cannot_accept_twice(self, client, customer_user, vendor_user, product):
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user)).json()
        client.post(f"/negotiations/{created['id']}/accept", headers=auth_headers(vendor_user))
        resp = client.post(f"/negotiations/{created['id']}/accept", headers=auth_headers(vendor_user))
        assert resp.status_code == 400


class TestNegotiationWebSocket:
    def test_ws_round_trip_and_accept(self, client, customer_user, vendor_user, product):
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user)).json()
        session_id = created["id"]
        customer_token = create_access_token({"sub": str(customer_user.id)})
        vendor_token = create_access_token({"sub": str(vendor_user.id)})

        with client.websocket_connect(f"/negotiations/{session_id}/ws?token={customer_token}") as cust_ws, \
             client.websocket_connect(f"/negotiations/{session_id}/ws?token={vendor_token}") as vend_ws:
            cust_ws.send_json({"type": "text", "text": "Hello!"})
            assert cust_ws.receive_json()["text_content"] == "Hello!"
            assert vend_ws.receive_json()["text_content"] == "Hello!"

            vend_ws.send_json({"type": "accept"})
            cust_accept = cust_ws.receive_json()
            vend_ws.receive_json()
            assert cust_accept["message_type"] == "accept"
            assert cust_accept["amount"] == 800.0

        resp = client.get(f"/negotiations/{session_id}", headers=auth_headers(customer_user))
        assert resp.json()["status"] == "accepted"

    def test_ws_counter_offer_updates_session_price(self, client, customer_user, vendor_user, product):
        """Regression test: a vendor's counter-offer over WS must update
        current_offer_price, not just accept -- otherwise anything reading
        the session (e.g. the vendor inbox list) shows a stale price."""
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 500.0}, headers=auth_headers(customer_user)).json()
        session_id = created["id"]
        vendor_token = create_access_token({"sub": str(vendor_user.id)})

        with client.websocket_connect(f"/negotiations/{session_id}/ws?token={vendor_token}") as vend_ws:
            vend_ws.send_json({"type": "offer", "amount": 900.0, "text": "How about 900?"})
            echoed = vend_ws.receive_json()
            assert echoed["amount"] == 900.0

        resp = client.get(f"/negotiations/{session_id}", headers=auth_headers(customer_user))
        assert resp.json()["current_offer_price"] == 900.0

    def test_ws_rejects_non_participant(self, client, db, tenant, customer_user, product):
        from app.db.models import User
        from app.core.security import get_password_hash
        other = User(name="Other", email="other-ws@test.com", hashed_password=get_password_hash("x"),
                     role="customer", tenant_id=tenant.id)
        db.add(other)
        db.commit()
        db.refresh(other)

        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user)).json()
        other_token = create_access_token({"sub": str(other.id)})

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/negotiations/{created['id']}/ws?token={other_token}") as ws:
                ws.receive_json()
