"""Post-deploy check: live notifications work across API processes and from the worker.

    python deploy/verify_realtime.py https://your-domain        (use https://localhost for local)

Creates a throwaway organization, then verifies (a) pushes caused by API
requests reach a WebSocket no matter which API process handled the request and
(b) a push caused by the background worker (an SLA breach) arrives via Redis.
Takes about two minutes because (b) waits for a real 1-minute SLA to breach.
"""
import asyncio
import json
import ssl
import sys
import time
import uuid

try:
    import httpx2 as httpx
except ModuleNotFoundError:  # pragma: no cover
    import httpx
import websockets

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://localhost").rstrip("/")
API = f"{BASE}/api/v1"
PW = "Realtime-Check-1"
run = uuid.uuid4().hex[:6]
ssl_ctx = ssl.create_default_context()
LOCAL = "://localhost" in BASE
if LOCAL:  # Caddy's internal CA
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE


async def open_socket(token: str):
    ws = await websockets.connect(BASE.replace("https://", "wss://") + "/api/v1/notifications/ws", ssl=ssl_ctx)
    await ws.send(json.dumps({"type": "auth", "token": token}))
    assert json.loads(await ws.recv()) == {"type": "ready"}
    return ws


async def main():
    async with httpx.AsyncClient(verify=not LOCAL, timeout=30) as http:
        r = await http.post(f"{API}/auth/register", json={
            "name": "RT Admin", "email": f"admin.{run}@rt.example.com", "password": PW, "organization_name": f"RT {run}"})
        admin = {"Authorization": f"Bearer {r.json()['access_token']}"}
        # Tight SLA so the worker records a breach quickly.
        r = await http.put(f"{API}/sla-policies", headers=admin, json={"policies": [
            {"priority": "critical", "first_response_minutes": 1, "resolution_minutes": 2}]})
        assert r.status_code == 200, r.text
        inv = (await http.post(f"{API}/organizations/me/invitations", headers=admin,
                               json={"email": f"agent.{run}@rt.example.com", "role": "agent"})).json()
        tok = inv["invite_url"].split("token=")[1]
        async with httpx.AsyncClient(verify=not LOCAL, timeout=30) as http2:
            r = await http2.post(f"{API}/auth/accept-invitation", json={"token": tok, "name": "RT Agent", "password": PW})
            agent_token = r.json()["access_token"]
        agent_id = (await http.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {agent_token}"})).json()["id"]
        admin_token = admin["Authorization"].split()[1]

        agent_ws = await open_socket(agent_token)
        admin_ws = await open_socket(admin_token)

        # (a) API-originated pushes, handled by either of 2 API processes.
        t = (await http.post(f"{API}/tickets", headers=admin, json={
            "title": "Realtime check", "description": "server down for everyone", "priority": "critical"})).json()
        n = 6
        for i in range(n):
            target = agent_id if i % 2 == 0 else None
            r = await http.post(f"{API}/tickets/{t['id']}/assign", headers=admin, json={"assignee_id": target})
            assert r.status_code == 200, r.text
        received = 0
        deadline = time.time() + 20
        while received < n // 2 and time.time() < deadline:
            msg = json.loads(await asyncio.wait_for(agent_ws.recv(), timeout=20))
            if msg.get("data", {}).get("type") == "ticket_assigned":
                received += 1
        print(f"(a) assignments pushed to agent: {received}/{n // 2}")

        # (b) Worker-originated push: SLA breach recorded by the worker process.
        await http.post(f"{API}/tickets/{t['id']}/assign", headers=admin, json={"assignee_id": None})
        started = time.time()
        got = None
        while time.time() - started < 200:
            try:
                msg = json.loads(await asyncio.wait_for(admin_ws.recv(), timeout=10))
            except asyncio.TimeoutError:
                continue
            if msg.get("data", {}).get("type") == "sla_breach":
                got = msg["data"]["title"]
                break
        print(f"(b) worker SLA-breach push to admin after {time.time() - started:.0f}s: {got}")
        await agent_ws.close()
        await admin_ws.close()
        assert received == n // 2 and got


asyncio.run(main())
