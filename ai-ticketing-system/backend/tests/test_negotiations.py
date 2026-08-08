"""
Tests for the rule-based negotiation engine, REST negotiation endpoints,
the WebSocket chat round trip, and the (mocked) LLM-assisted path.
"""
import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token
from app.db.models import NegotiationMessage
from app.services.negotiation_ai import rule_based_response
import app.services.negotiation_ai as neg_ai
from tests.conftest import auth_headers


def _msg(sender_role, message_type, amount=None, text=None):
    return NegotiationMessage(sender_role=sender_role, message_type=message_type, amount=amount, text_content=text)


class TestRuleBasedEngine:
    def test_accepts_when_offer_meets_floor(self, product):
        result = rule_based_response(product, [], 700.0)
        assert result["message_type"] == "accept"
        assert result["amount"] == 700.0

    def test_accepts_above_floor(self, product):
        result = rule_based_response(product, [], 850.0)
        assert result["message_type"] == "accept"

    def test_counters_below_floor_with_exact_floor_price(self, product):
        # Below floor -> counter is the vendor's exact floor price, never a
        # computed number neither side proposed (previously this averaged
        # the listed price and the customer's offer, e.g. 500 -> 750).
        result = rule_based_response(product, [], 500.0)
        assert result["message_type"] == "counter_offer"
        assert result["amount"] == product.floor_price == 700.0

    def test_counter_ignores_prior_round_history(self, product):
        # No multi-round convergence: however many rounds have already
        # happened, a still-below-floor offer always gets the same floor
        # counter, not a gradually-shrinking one.
        history = [_msg("ai_assistant", "counter_offer", amount=750.0) for _ in range(5)]
        result = rule_based_response(product, history, 500.0)
        assert result["message_type"] == "counter_offer"
        assert result["amount"] == product.floor_price

    def test_default_floor_when_unset(self, db, tenant, vendor):
        from app.db.models import Product
        p = Product(tenant_id=tenant.id, vendor_id=vendor.id, title="No Floor", description="x",
                    price=1000.0, currency="INR", stock_quantity=5, status="active")
        db.add(p)
        db.commit()
        db.refresh(p)
        # default floor = price * 0.8 = 800
        result = rule_based_response(p, [], 750.0)
        assert result["message_type"] == "counter_offer"


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

    def test_auto_negotiate_triggers_assistant_response(self, client, db, customer_user, product):
        product.auto_negotiate_enabled = True
        db.commit()
        resp = client.post("/negotiations/", json={"product_id": product.id, "amount": 500.0}, headers=auth_headers(customer_user))
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["messages"]) == 2
        assert data["messages"][1]["sender_role"] == "ai_assistant"

    def test_auto_negotiate_counter_updates_session_price(self, client, db, customer_user, product):
        """
        Regression test: current_offer_price used to only get set at session
        creation (the customer's opening offer) and on accept -- a vendor
        scanning their inbox saw the original offer forever, never the
        assistant's counter, even though the chat itself had moved on.
        """
        product.auto_negotiate_enabled = True
        db.commit()
        resp = client.post("/negotiations/", json={"product_id": product.id, "amount": 500.0}, headers=auth_headers(customer_user))
        data = resp.json()
        counter_amount = data["messages"][1]["amount"]
        assert counter_amount != 500.0
        assert data["current_offer_price"] == counter_amount

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

    def test_ws_auto_negotiate_broadcasts_assistant_reply(self, client, db, customer_user, product):
        product.auto_negotiate_enabled = True
        db.commit()
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 500.0}, headers=auth_headers(customer_user)).json()
        session_id = created["id"]
        customer_token = create_access_token({"sub": str(customer_user.id)})

        with client.websocket_connect(f"/negotiations/{session_id}/ws?token={customer_token}") as ws:
            ws.send_json({"type": "offer", "amount": 550.0})
            own_echo = ws.receive_json()
            ai_reply = ws.receive_json()
            assert own_echo["sender_role"] == "customer"
            assert ai_reply["sender_role"] == "ai_assistant"


class TestLLMAssistedPath:
    """Mocks the anthropic client so this exercises the wiring without a network call."""

    def test_llm_path_used_when_configured(self, product, vendor, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

        class FakeResponse:
            parsed_output = neg_ai.NegotiationDecision(action="counter_offer", amount=750.0, message="How about 750?")

        class FakeMessages:
            def parse(self, **kwargs):
                return FakeResponse()

        class FakeClient:
            def __init__(self, api_key=None):
                self.messages = FakeMessages()

        monkeypatch.setattr(neg_ai.anthropic, "Anthropic", FakeClient)

        result = asyncio.run(neg_ai.llm_assisted_response(product, vendor, [], 500.0))
        assert result == {"message_type": "counter_offer", "amount": 750.0, "text_content": "How about 750?"}

    def test_llm_path_falls_back_to_none_on_error(self, product, vendor, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "anthropic_api_key", "test-key")

        class BrokenClient:
            def __init__(self, api_key=None):
                raise RuntimeError("network error")

        monkeypatch.setattr(neg_ai.anthropic, "Anthropic", BrokenClient)

        result = asyncio.run(neg_ai.llm_assisted_response(product, vendor, [], 500.0))
        assert result is None

    def test_no_api_key_skips_llm(self, product, vendor, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "anthropic_api_key", None)
        result = asyncio.run(neg_ai.llm_assisted_response(product, vendor, [], 500.0))
        assert result is None
