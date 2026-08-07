"""
Tests for the notification system: category-based ticket routing, alert
delivery on ticket bargaining / marketplace negotiation / order events,
the REST inbox endpoints, tenant isolation, and the WebSocket push channel.
"""
from app.core.security import create_access_token
from app.db.models import User, Vendor
from app.core.security import get_password_hash
from tests.conftest import auth_headers


def _create_ticket(client, user, tenant_id, title="Test ticket", description="Something broke"):
    return client.post("/tickets/", json={
        "title": title,
        "description": description,
        "tenant_id": tenant_id,
    }, headers=auth_headers(user))


def _notifications_for(client, user):
    return client.get("/notifications/", headers=auth_headers(user)).json()


class TestProviderCategoryPreferences:
    def test_provider_can_set_and_get_categories(self, client, provider_user):
        resp = client.put("/users/me/categories", json={"categories": ["Electrical", "Plumbing"]},
                           headers=auth_headers(provider_user))
        assert resp.status_code == 200
        assert resp.json()["categories"] == ["Electrical", "Plumbing"]

        resp = client.get("/users/me/categories", headers=auth_headers(provider_user))
        assert resp.status_code == 200
        assert resp.json()["categories"] == ["Electrical", "Plumbing"]

    def test_set_categories_dedupes_and_sorts(self, client, provider_user):
        resp = client.put("/users/me/categories", json={"categories": ["Plumbing", "Electrical", "Plumbing"]},
                           headers=auth_headers(provider_user))
        assert resp.json()["categories"] == ["Electrical", "Plumbing"]

    def test_customer_cannot_set_categories(self, client, customer_user):
        resp = client.put("/users/me/categories", json={"categories": ["Electrical"]},
                           headers=auth_headers(customer_user))
        assert resp.status_code == 403

    def test_set_categories_replaces_previous(self, client, provider_user):
        client.put("/users/me/categories", json={"categories": ["Electrical"]}, headers=auth_headers(provider_user))
        resp = client.put("/users/me/categories", json={"categories": ["Medical"]}, headers=auth_headers(provider_user))
        assert resp.json()["categories"] == ["Medical"]


class TestTicketCreationRouting:
    def test_provider_with_matching_category_gets_notified(self, client, customer_user, provider_user, tenant):
        client.put("/users/me/categories", json={"categories": ["IT Support"]}, headers=auth_headers(provider_user))
        resp = _create_ticket(client, customer_user, tenant.id, title="WiFi outage", description="Network is not working")
        assert resp.json()["category"] == "IT Support"

        notes = _notifications_for(client, provider_user)
        assert any(n["type"] == "ticket_created" for n in notes)

    def test_provider_with_non_matching_category_not_notified(self, client, customer_user, provider_user, tenant):
        client.put("/users/me/categories", json={"categories": ["Plumbing"]}, headers=auth_headers(provider_user))
        _create_ticket(client, customer_user, tenant.id, title="WiFi outage", description="Network is not working")

        notes = _notifications_for(client, provider_user)
        assert not any(n["type"] == "ticket_created" for n in notes)

    def test_provider_with_no_preferences_gets_everything(self, client, customer_user, provider_user, tenant):
        # provider_user has never called PUT /users/me/categories -- generalist fallback
        _create_ticket(client, customer_user, tenant.id, title="WiFi outage", description="Network is not working")

        notes = _notifications_for(client, provider_user)
        assert any(n["type"] == "ticket_created" for n in notes)

    def test_opted_in_provider_not_used_as_fallback_for_other_categories(self, client, db, tenant, customer_user, provider_user):
        # Once a provider opts into a category, they should NOT also catch
        # unrelated categories via the "nobody has preferences" fallback path.
        client.put("/users/me/categories", json={"categories": ["Electrical"]}, headers=auth_headers(provider_user))
        _create_ticket(client, customer_user, tenant.id, title="WiFi outage", description="Network is not working")

        notes = _notifications_for(client, provider_user)
        assert not any(n["type"] == "ticket_created" for n in notes)


class TestTicketBargainingNotifications:
    def test_offer_notifies_counterpart(self, client, customer_user, provider_user, tenant):
        ticket = _create_ticket(client, customer_user, tenant.id).json()
        client.post(f"/tickets/provider/offer/{ticket['id']}", headers=auth_headers(provider_user))

        resp = client.post(f"/tickets/{ticket['id']}/bargaining/offer", json={"amount": 500, "message": "My budget"},
                            headers=auth_headers(customer_user))
        assert resp.status_code == 201

        notes = _notifications_for(client, provider_user)
        assert any(n["type"] == "ticket_offer" for n in notes)

    def test_accept_notifies_counterpart(self, client, customer_user, provider_user, tenant):
        ticket = _create_ticket(client, customer_user, tenant.id).json()
        client.post(f"/tickets/provider/offer/{ticket['id']}", headers=auth_headers(provider_user))
        client.post(f"/tickets/{ticket['id']}/bargaining/offer", json={"amount": 500},
                     headers=auth_headers(customer_user))

        resp = client.post(f"/tickets/{ticket['id']}/bargaining/accept", json={"message": "Deal"},
                            headers=auth_headers(provider_user))
        assert resp.status_code == 200

        notes = _notifications_for(client, customer_user)
        assert any(n["type"] == "ticket_accepted" for n in notes)

    def test_reject_notifies_counterpart(self, client, customer_user, provider_user, tenant):
        ticket = _create_ticket(client, customer_user, tenant.id).json()
        client.post(f"/tickets/provider/offer/{ticket['id']}", headers=auth_headers(provider_user))
        client.post(f"/tickets/{ticket['id']}/bargaining/offer", json={"amount": 500},
                     headers=auth_headers(customer_user))

        resp = client.post(f"/tickets/{ticket['id']}/bargaining/reject", json={"message": "Too low"},
                            headers=auth_headers(provider_user))
        assert resp.status_code == 200

        notes = _notifications_for(client, customer_user)
        assert any(n["type"] == "ticket_rejected" for n in notes)


class TestMarketplaceNegotiationNotifications:
    def test_start_negotiation_notifies_vendor(self, client, customer_user, vendor_user, product):
        resp = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0},
                            headers=auth_headers(customer_user))
        assert resp.status_code == 201

        notes = _notifications_for(client, vendor_user)
        assert any(n["type"] == "negotiation_started" for n in notes)

    def test_accept_notifies_customer(self, client, customer_user, vendor_user, product):
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0},
                               headers=auth_headers(customer_user)).json()
        resp = client.post(f"/negotiations/{created['id']}/accept", headers=auth_headers(vendor_user))
        assert resp.status_code == 200

        notes = _notifications_for(client, customer_user)
        assert any(n["type"] == "negotiation_accepted" for n in notes)

    def test_ws_message_notifies_counterpart(self, client, customer_user, vendor_user, product):
        created = client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0},
                               headers=auth_headers(customer_user)).json()
        session_id = created["id"]
        vendor_token = create_access_token({"sub": str(vendor_user.id)})
        customer_token = create_access_token({"sub": str(customer_user.id)})

        with client.websocket_connect(f"/negotiations/{session_id}/ws?token={customer_token}") as cust_ws, \
             client.websocket_connect(f"/negotiations/{session_id}/ws?token={vendor_token}") as vend_ws:
            vend_ws.send_json({"type": "text", "text": "How about 850?"})
            cust_ws.receive_json()
            vend_ws.receive_json()

        notes = _notifications_for(client, customer_user)
        assert any(n["type"] == "negotiation_message" for n in notes)


class TestOrderNotifications:
    def test_create_order_notifies_vendor(self, client, customer_user, vendor_user, product):
        resp = client.post("/orders/", json={"product_id": product.id, "quantity": 1},
                            headers=auth_headers(customer_user))
        assert resp.status_code == 201

        notes = _notifications_for(client, vendor_user)
        assert any(n["type"] == "order_placed" for n in notes)

    def test_status_update_notifies_customer(self, client, customer_user, vendor_user, product):
        order = client.post("/orders/", json={"product_id": product.id, "quantity": 1},
                             headers=auth_headers(customer_user)).json()
        resp = client.put(f"/orders/{order['id']}/status?new_status=confirmed", headers=auth_headers(vendor_user))
        assert resp.status_code == 200

        notes = _notifications_for(client, customer_user)
        assert any(n["type"] == "order_status_changed" for n in notes)


class TestNotificationInboxEndpoints:
    def test_unread_count_and_mark_read(self, client, customer_user, vendor_user, product):
        client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user))
        resp = client.get("/notifications/unread-count", headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

        note_id = _notifications_for(client, vendor_user)[0]["id"]
        resp = client.put(f"/notifications/{note_id}/read", headers=auth_headers(vendor_user))
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True

    def test_mark_all_read(self, client, customer_user, vendor_user, product):
        client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user))
        client.post("/orders/", json={"product_id": product.id, "quantity": 1}, headers=auth_headers(customer_user))

        resp = client.put("/notifications/read-all", headers=auth_headers(vendor_user))
        assert resp.status_code == 200

        count_resp = client.get("/notifications/unread-count", headers=auth_headers(vendor_user))
        assert count_resp.json()["count"] == 0

    def test_cannot_mark_others_notification_read(self, client, db, tenant, customer_user, vendor_user, product):
        client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user))
        note_id = _notifications_for(client, vendor_user)[0]["id"]

        resp = client.put(f"/notifications/{note_id}/read", headers=auth_headers(customer_user))
        assert resp.status_code == 404

    def test_tenant_isolation(self, client, db, customer_user, vendor_user, product):
        from app.db.models import Tenant
        other_tenant = Tenant(name="Other Org", domain="other.example.com")
        db.add(other_tenant)
        db.commit()
        db.refresh(other_tenant)

        other_vendor_user = User(name="Other Vendor", email="other-vendor-notif@test.com",
                                  hashed_password=get_password_hash("x"), role="vendor", tenant_id=other_tenant.id)
        db.add(other_vendor_user)
        db.commit()
        db.refresh(other_vendor_user)
        other_vendor = Vendor(user_id=other_vendor_user.id, tenant_id=other_tenant.id, shop_name="Other Shop",
                               phone_number="+91-1", shop_address="Elsewhere")
        db.add(other_vendor)
        db.commit()

        client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0}, headers=auth_headers(customer_user))

        notes = _notifications_for(client, other_vendor_user)
        assert notes == []


class TestNotificationWebSocket:
    def test_ws_push_on_negotiation_start(self, client, customer_user, vendor_user, product):
        vendor_token = create_access_token({"sub": str(vendor_user.id)})
        with client.websocket_connect(f"/notifications/ws?token={vendor_token}") as ws:
            client.post("/negotiations/", json={"product_id": product.id, "amount": 800.0},
                         headers=auth_headers(customer_user))
            payload = ws.receive_json()
            assert payload["type"] == "negotiation_started"
