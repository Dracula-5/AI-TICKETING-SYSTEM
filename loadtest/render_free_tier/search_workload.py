"""Search-heavy workload: 60 KB searches, 10 related-article lookups, 10 new tickets (triage).

usage: python search_workload.py BASE_URL ADMIN_EMAIL CUSTOMER_EMAIL PASSWORD
See reports/render_free_tier.md.
"""

import sys
import time

import httpx

base, admin_email, customer_email, password = sys.argv[1:5]
_c = httpx.Client(base_url=base, timeout=300)


def call(method, *a, **kw):
    for attempt in range(3):
        try:
            return getattr(_c, method)(*a, **kw)
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
            if attempt == 2:
                raise
            time.sleep(2)


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def login(email):
    r = call(
        "post", "/api/v1/auth/login", data={"username": email, "password": password}
    )
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


admin, customer = login(admin_email), login(customer_email)
log("logged in")
queries = [
    "vpn error E1003",
    "printer jam",
    "reset password link expired",
    "laptop slow boot",
    "MFA badge",
    "teams call drops",
    "SAP login",
    "wifi keeps disconnecting",
    "email not syncing",
    "badge not working",
]
lat = []
for q in queries * 6:
    s = time.time()
    call(
        "get", "/api/v1/kb/search", headers=customer, params={"q": q}
    ).raise_for_status()
    lat.append(time.time() - s)
lat.sort()
log(
    f"KB search x{len(lat)}: p50 {lat[len(lat) // 2]:.2f}s p95 {lat[int(len(lat) * 0.95)]:.2f}s"
)
ids = []
for i in range(10):
    r = call(
        "post",
        "/api/v1/tickets",
        headers=customer,
        json={
            "title": f"{queries[i]} problem {i}",
            "description": f"Since today: {queries[i]}. Please help.",
        },
    )
    r.raise_for_status()
    ids.append(r.json()["id"])
for tid in ids:
    call("get", f"/api/v1/tickets/{tid}/ai/knowledge", headers=admin)
pending, t = set(ids), time.time()
while pending and time.time() - t < 600:
    for tid in list(pending):
        r = call("get", f"/api/v1/tickets/{tid}/ai", headers=admin)
        if r.status_code == 200 and r.json().get("predictions"):
            pending.discard(tid)
    if pending:
        time.sleep(5)
log(f"triaged {len(ids) - len(pending)}/{len(ids)}")
print("done", flush=True)
