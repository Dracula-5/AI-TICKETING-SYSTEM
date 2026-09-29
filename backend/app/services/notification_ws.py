"""
In-memory WebSocket registry for the live notification feed — one entry per
signed-in user, every open tab receives the push.

Single-instance only: with more than one API process, a push reaches only the
sockets connected to the process that committed the change. Multi-instance
fan-out needs a shared pub/sub layer (Redis), planned with the worker in P2.
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
