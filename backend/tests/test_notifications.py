from app.core.security import create_access_token
from app.db.models import Notification
from tests.conftest import assign, auth, create_ticket

API = "/api/v1/notifications"


class TestInbox:
    def test_list_count_and_mark_read(self, client, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assign(client, manager_a, tid, agent_a.id)
        items = client.get(API, headers=auth(agent_a)).json()
        assert len(items) == 1 and items[0]["type"] == "ticket_assigned" and items[0]["link"] == f"/tickets/{tid}"
        assert client.get(f"{API}/unread-count", headers=auth(agent_a)).json() == {"count": 1}
        assert client.put(f"{API}/{items[0]['id']}/read", headers=auth(agent_a)).json()["is_read"] is True
        assert client.get(f"{API}/unread-count", headers=auth(agent_a)).json() == {"count": 0}

    def test_mark_all_read(self, client, db, org_a, agent_a):
        for i in range(3):
            db.add(Notification(tenant_id=org_a.id, user_id=agent_a.id, type="x", title=f"n{i}"))
        db.commit()
        client.put(f"{API}/read-all", headers=auth(agent_a))
        assert client.get(f"{API}/unread-count", headers=auth(agent_a)).json() == {"count": 0}

    def test_rolled_back_change_creates_no_notification(self, client, db, manager_a, customer_a, agent_b):
        tid = create_ticket(client, customer_a)["id"]
        assert assign(client, manager_a, tid, agent_b.id).status_code == 404
        assert db.query(Notification).filter(Notification.user_id == agent_b.id).count() == 0


class TestWebSocket:
    def test_auth_by_first_message_then_push(self, client, manager_a, agent_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        token, _ = create_access_token(agent_a.id, agent_a.tenant_id, agent_a.role)
        with client.websocket_connect(f"{API}/ws") as ws:
            ws.send_json({"type": "auth", "token": token})
            assert ws.receive_json() == {"type": "ready"}
            assign(client, manager_a, tid, agent_a.id)
            msg = ws.receive_json()
            assert msg["type"] == "notification" and msg["data"]["type"] == "ticket_assigned"

    def test_bad_token_is_rejected(self, client):
        import pytest
        from starlette.websockets import WebSocketDisconnect

        with client.websocket_connect(f"{API}/ws") as ws:
            ws.send_json({"type": "auth", "token": "nope"})
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 1008
