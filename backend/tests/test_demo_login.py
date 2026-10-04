"""Public-demo sign-in: visitors may enter the seeded accounts of the demo
organization without a password — and nothing else."""

import pytest

from app.core.config import settings
from app.db.models import AuditLog, User
from app.scripts import seed_demo
from tests.conftest import auth

API = "/api/v1"


@pytest.fixture()
def demo_org(db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "Demo-Passw0rd!")
    monkeypatch.setattr(seed_demo, "TICKETS_PER_ORG", 4)
    seed_demo.seed()


@pytest.fixture()
def demo_on(monkeypatch):
    monkeypatch.setattr(settings, "demo_login_enabled", True)


def test_off_by_default(client, demo_org):
    assert client.get(f"{API}/auth/demo").json() == {"enabled": False, "accounts": []}
    r = client.post(f"{API}/auth/demo-login", json={"email": "morgan.manager@helix-health.example.com"})
    assert r.status_code == 404


def test_on_with_seed_on_start_too(client, demo_org, monkeypatch):
    monkeypatch.setattr(settings, "seed_demo_on_start", True)
    assert client.get(f"{API}/auth/demo").json()["enabled"] is True


def test_nothing_offered_without_a_demo_organization(client, demo_on, customer_a):
    assert client.get(f"{API}/auth/demo").json() == {"enabled": False, "accounts": []}


def test_lists_the_seeded_accounts_and_signs_in(client, db, demo_org, demo_on):
    body = client.get(f"{API}/auth/demo").json()
    assert body["enabled"] is True
    # Every role the seed creates is offered, from one organization, in display order.
    assert [a["role"] for a in body["accounts"]] == ["manager", "agent", "customer", "org_admin", "analyst"]
    assert {a["organization"] for a in body["accounts"]} == {"Helix Health (Demo)"}
    assert all(a["email"].endswith("@helix-health.example.com") for a in body["accounts"])

    manager = body["accounts"][0]
    r = client.post(f"{API}/auth/demo-login", json={"email": manager["email"]})
    assert r.status_code == 200 and "nexadesk_refresh" in r.headers.get("set-cookie", "")
    token = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = client.get(f"{API}/auth/me", headers=token).json()
    assert me["role"] == "manager" and me["organization"]["is_demo"] is True
    assert client.get(f"{API}/tickets", headers=token).json()["total"] == 4
    assert db.query(AuditLog).filter(AuditLog.action == "auth.demo_login").count() == 1


def test_only_the_seeded_accounts_can_be_entered(client, db, demo_org, demo_on, customer_a, platform_admin):
    def demo_login(email):
        return client.post(f"{API}/auth/demo-login", json={"email": email}).status_code

    # A member of a real organization, the platform administrator, an unknown address.
    assert demo_login(customer_a.email) == 404
    assert demo_login(platform_admin.email) == 404
    assert demo_login("nobody@example.com") == 404
    # Seeded accounts of the other demo organizations are not offered either.
    assert demo_login("morgan.manager@brightline.example.com") == 404
    # Someone who joined the offered organization on their own has a password of their own.
    offered = client.get(f"{API}/auth/demo").json()["accounts"][0]
    tenant_id = db.query(User).filter(User.email == offered["email"]).one().tenant_id
    visitor = User(
        name="Visitor",
        email="visitor@helix-health.example.com",
        hashed_password="x",
        role="customer",
        tenant_id=tenant_id,
        data_origin="demo",
    )
    db.add(visitor)
    db.commit()
    assert demo_login(visitor.email) == 404
    assert client.get(f"{API}/auth/me", headers=auth(visitor)).status_code == 200  # the account itself is fine
