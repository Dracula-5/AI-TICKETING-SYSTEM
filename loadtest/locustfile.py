"""
NexaDesk load profile (P10). SYNTHETIC traffic against the load-test organization
created by `python -m app.scripts.seed_volume`.

Three kinds of users with think time between actions, weighted like a service
desk: many requesters, fewer agents, a few managers. Every request is named by
endpoint group so results aggregate per group.

    TOKENS=loadtest/tokens.json locust -f loadtest/locustfile.py --host https://localhost

Tokens are minted by the seeder (see its docstring): login is rate-limited and
bcrypt-bound by design and is measured separately, not in this profile.
"""

import json
import os
import random
from urllib.parse import quote

from locust import between, events, task
from locust.contrib.fasthttp import FastHttpUser

TOKENS = json.load(open(os.environ.get("TOKENS", "loadtest/tokens.json"), encoding="utf-8"))
API = "/api/v1"
SEARCHES = ["vpn", "printer", "password", "outlook", "monitor", "wifi", "#12", "access"]
KB_QUERIES = ["vpn disconnects on wifi", "reset my password", "printer jams", "outlook crashes"]
TITLES = [("Laptop will not charge", "The charger light is off and the battery stays at 3%."),
          ("VPN error 809 at home", "The VPN client shows error 809 when I connect from home."),
          ("Need access to the HR share", "Please give me read access to the HR shared folder.")]
_pools: dict[str, list] = {role: list(users) for role, users in TOKENS["users"].items()}


def _token(role: str) -> str:
    pool = _pools[role] or list(TOKENS["users"][role])
    return random.choice(pool)["token"]


class Base(FastHttpUser):
    abstract = True
    insecure = True  # Caddy's internal CA for DOMAIN=localhost
    role = "customer"

    def on_start(self):
        self.headers = {"Authorization": f"Bearer {_token(self.role)}"}
        self.ticket_ids: list[int] = []

    def get(self, path, name, **kw):
        with self.client.get(f"{API}{path}", headers=self.headers, name=name, catch_response=True, **kw) as r:
            if r.status_code == 429:  # per-IP limit: every virtual user shares one IP
                r.success()
                r.request_meta["name"] = f"{name} (429 per-IP limit, expected)"
            elif r.status_code != 200:
                r.failure(f"{r.status_code}")
            return r

    def remember(self, r):
        try:
            self.ticket_ids = [t["id"] for t in r.json()["items"]][:25] or self.ticket_ids
        except Exception:  # noqa: BLE001 -- failure already recorded
            pass


class Requester(Base):
    weight = 6
    wait_time = between(3, 8)
    role = "customer"

    @task(5)
    def my_tickets(self):
        self.remember(self.get("/tickets?requester=me&page_size=25", "GET /tickets (requester)"))

    @task(3)
    def view_ticket(self):
        if self.ticket_ids:
            tid = random.choice(self.ticket_ids)
            self.get(f"/tickets/{tid}", "GET /tickets/{id}")
            self.get(f"/tickets/{tid}/comments", "GET /tickets/{id}/comments")

    @task(2)
    def kb_search(self):
        self.get(f"/kb/search?q={quote(random.choice(KB_QUERIES))}", "GET /kb/search")

    @task(1)
    def create_ticket(self):
        title, desc = random.choice(TITLES)
        # All virtual users share one IP, so the per-IP creation limit (30/min) is expected to
        # trigger; those responses are reported under their own name, not as failures.
        with self.client.post(f"{API}/tickets", json={"title": title, "description": desc}, headers=self.headers,
                              name="POST /tickets", catch_response=True) as r:
            if r.status_code == 429:
                r.success()
                r.request_meta["name"] = "POST /tickets (429 per-IP limit, expected)"
            elif r.status_code != 201:
                r.failure(f"{r.status_code}")


class Agent(Base):
    weight = 3
    wait_time = between(2, 6)
    role = "agent"

    @task(3)
    def queue(self):
        self.remember(self.get("/tickets?status=open&assignee=unassigned&page_size=25", "GET /tickets (queue)"))

    @task(3)
    def my_work(self):
        self.remember(self.get("/tickets?status=open&assignee=me&page_size=25", "GET /tickets (my work)"))

    @task(4)
    def ticket_page(self):
        if not self.ticket_ids:
            return
        tid = random.choice(self.ticket_ids)
        self.get(f"/tickets/{tid}", "GET /tickets/{id}")
        self.get(f"/tickets/{tid}/comments", "GET /tickets/{id}/comments")
        self.get(f"/tickets/{tid}/history", "GET /tickets/{id}/history")
        self.get(f"/tickets/{tid}/ai", "GET /tickets/{id}/ai")

    @task(1)
    def search(self):
        self.get(f"/tickets?q={quote(random.choice(SEARCHES))}&page_size=25", "GET /tickets?q= (search)")

    @task(1)
    def comment(self):
        if self.ticket_ids:
            self.client.post(f"{API}/tickets/{random.choice(self.ticket_ids)}/comments", headers=self.headers,
                             json={"content": "Looking into it.", "visibility": "internal"},
                             name="POST /tickets/{id}/comments")


class Manager(Base):
    weight = 1
    wait_time = between(5, 10)
    role = "manager"

    @task(3)
    def dashboard(self):
        self.get("/analytics/overview", "GET /analytics/overview")

    @task(2)
    def sla_monitor(self):
        self.get("/tickets?sla=at_risk&page_size=25", "GET /tickets (SLA at risk)")

    @task(1)
    def ai_performance(self):
        self.get("/analytics/ai-performance", "GET /analytics/ai-performance")


@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--label", default="", help="free-text label stored with the run")
