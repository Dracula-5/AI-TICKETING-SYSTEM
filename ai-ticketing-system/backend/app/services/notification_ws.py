"""
In-memory WebSocket connection registry for the live notification feed.
One entry per logged-in user (as opposed to negotiation_ws.py's one entry
per chat session) -- every tab a user has open receives the same push.

Single-instance only, same caveat as negotiation_ws.py: fine for the
current single-instance deployment; multi-instance fanout would need a
shared pub/sub layer (Redis) in a later phase.
"""
from fastapi import WebSocket


class NotificationConnectionManager:
    def __init__(self):
        self.active: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        self.active.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        connections = self.active.get(user_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.active.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: dict):
        for connection in list(self.active.get(user_id, [])):
            try:
                await connection.send_json(payload)
            except Exception:
                self.disconnect(user_id, connection)


manager = NotificationConnectionManager()
