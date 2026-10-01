"""Exercise the AI paths of a running API (Render-like container) and report timings:
a 0.6 MB / 800-chunk synthetic KB document, 30 tickets with triage, 20 KB searches, dashboards.

usage: [KB_DOC_ID=1] python ai_workload.py BASE_URL ADMIN_EMAIL CUSTOMER_EMAIL PASSWORD
See reports/render_free_tier.md.
"""

import json
import os
import sys
import time

import httpx

base, admin_email, customer_email, password = sys.argv[1:5]
_c = httpx.Client(base_url=base, timeout=300)


class _Retry:
    """Retry requests whose keep-alive connection the server closed meanwhile."""

    def __getattr__(self, name):
        fn = getattr(_c, name)

        def call(*a, **kw):
            for attempt in range(3):
                try:
                    return fn(*a, **kw)
                except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
                    if attempt == 2:
                        raise
                    time.sleep(2)

        return call


c = _Retry()


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def login(email):
    t = time.time()
    r = c.post("/api/v1/auth/login", data={"username": email, "password": password})
    r.raise_for_status()
    log(f"login {email} {time.time() - t:.1f}s")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


admin = login(admin_email)
customer = login(customer_email)

# 1. Knowledge base: a ~1 MB Markdown handbook (stress case for chunk embedding).
topics = [
    "VPN",
    "printer",
    "password reset",
    "laptop",
    "email",
    "Wi-Fi",
    "MFA",
    "SAP",
    "Teams",
    "badge",
]
parts = []
for i in range(400):
    t = topics[i % len(topics)]
    parts.append(
        f"## {t.title()} procedure {i}\n\n"
        + (
            f"If the {t} fails with error E{1000 + i}, first restart the device, then check the "
            f"{t} settings page and confirm the account is active. Escalate to the service desk "
            f"with the error code and a screenshot if the problem persists after thirty minutes. "
        )
        * 6
        + "\n"
    )
doc = "# IT handbook (synthetic)\n\n" + "\n".join(parts)
t = time.time()
if os.environ.get("KB_DOC_ID"):  # continue with a document uploaded by an earlier run
    doc_id = int(os.environ["KB_DOC_ID"])
else:
    log(f"KB upload {len(doc) / 1e6:.2f} MB")
    r = c.post(
        "/api/v1/kb/documents",
        headers=admin,
        files={"file": ("handbook.md", doc.encode(), "text/markdown")},
        data={"visibility": "public", "title": "IT handbook (synthetic)"},
    )
    r.raise_for_status()
    doc_id = r.json()["id"]
while True:
    d = c.get(f"/api/v1/kb/documents/{doc_id}", headers=admin).json()
    if d.get("status") not in ("pending", "processing", "queued"):
        break
    time.sleep(5)
log(
    f"KB document status={d.get('status')} chunks={d.get('chunk_count')} after {time.time() - t:.0f}s"
)

# 2. Tickets: each one queues triage (embedding + kNN + playbook agent).
texts = [
    (
        "VPN keeps disconnecting",
        "Since this morning the VPN drops every few minutes with error E1003.",
    ),
    (
        "Printer on floor 2 jams",
        "The printer near the kitchen jams on every second page.",
    ),
    (
        "Cannot reset my password",
        "The reset link says it expired although I just requested it.",
    ),
    (
        "Laptop very slow after update",
        "After the latest update my laptop takes 10 minutes to boot.",
    ),
    (
        "Outlook not syncing",
        "My email has not synced since yesterday; new messages are missing.",
    ),
]
ids = []
t = time.time()
for i in range(30):
    title, desc = texts[i % len(texts)]
    r = c.post(
        "/api/v1/tickets",
        headers=customer,
        json={"title": f"{title} #{i}", "description": desc},
    )
    r.raise_for_status()
    ids.append(r.json()["id"])
log(f"created {len(ids)} tickets in {time.time() - t:.0f}s")

deadline = time.time() + 900
pending = set(ids)
while pending and time.time() < deadline:
    for tid in list(pending):
        r = c.get(f"/api/v1/tickets/{tid}/ai", headers=admin)
        if r.status_code == 200 and r.json().get("predictions"):
            pending.discard(tid)
    if pending:
        time.sleep(10)
log(
    f"tickets with AI recommendations: {len(ids) - len(pending)}/{len(ids)} after {time.time() - t:.0f}s"
)

# 3. Reads: KB search, related articles, dashboards.
lat = []
for q in [
    "vpn error E1003",
    "printer jam",
    "reset password link expired",
    "laptop slow boot",
    "MFA badge",
] * 4:
    s = time.time()
    r = c.get("/api/v1/kb/search", headers=customer, params={"q": q})
    r.raise_for_status()
    lat.append(time.time() - s)
lat.sort()
log(f"KB search x{len(lat)}: p50 {lat[len(lat) // 2]:.2f}s max {lat[-1]:.2f}s")
for path in [
    f"/api/v1/tickets/{ids[0]}/ai/knowledge",
    "/api/v1/analytics/overview",
    "/api/v1/ai/queue",
    "/api/v1/analytics/ai-performance",
    "/api/v1/analytics/kb",
]:
    s = time.time()
    r = c.get(path, headers=admin)
    log(f"GET {path} {r.status_code} {time.time() - s:.2f}s")
print(json.dumps({"done": True}))
