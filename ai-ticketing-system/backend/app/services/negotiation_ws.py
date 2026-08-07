"""
In-memory WebSocket connection registry for negotiation chat sessions.

Single-instance only: connections live in process memory, so this only
fans out messages to clients connected to *this* server process. Fine for
the current single-instance deployment (matches the existing SLA-monitor
background thread's assumption). Multi-instance fanout would need a shared
pub/sub layer (Redis) — that's a Phase 3 concern, not this one.
"""
from fastapi import WebSocket


class NegotiationConnectionManager:
    def __init__(self):
        self.active: dict[int, list[WebSocket]] = {}

    async def connect(self, session_id: int, websocket: WebSocket):
        self.active.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: int, websocket: WebSocket):
        connections = self.active.get(session_id)
        if not connections:
            return
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.active.pop(session_id, None)

    async def broadcast(self, session_id: int, payload: dict):
        for connection in list(self.active.get(session_id, [])):
            try:
                await connection.send_json(payload)
            except Exception:
                self.disconnect(session_id, connection)


manager = NegotiationConnectionManager()
