"""P11: dashboard aggregates are cached briefly per organization and fail open."""

from app.core.config import settings
from app.routers import analytics
from tests.conftest import auth, create_ticket


def test_overview_is_served_from_cache_within_ttl(client, monkeypatch, manager_a, manager_b, customer_a):
    store: dict = {}
    monkeypatch.setattr(analytics, "cache_get", lambda k: store.get(k))
    monkeypatch.setattr(analytics, "cache_set", lambda k, v, ttl: store.__setitem__(k, v))
    first = client.get("/api/v1/analytics/overview", headers=auth(manager_a)).json()
    create_ticket(client, customer_a)
    second = client.get("/api/v1/analytics/overview", headers=auth(manager_a)).json()
    assert second["open_tickets"] == first["open_tickets"] == 0  # cached for up to the TTL
    assert second["generated_at"] == first["generated_at"]  # the page shows when figures were computed
    # Per organization: another org never sees this org's cached figures.
    other = client.get("/api/v1/analytics/overview", headers=auth(manager_b)).json()
    assert len(store) == 2 and other["open_tickets"] == 0


def test_without_cache_figures_are_live(client, monkeypatch, manager_a, customer_a):
    monkeypatch.setattr(settings, "analytics_cache_seconds", 0)
    client.get("/api/v1/analytics/overview", headers=auth(manager_a))
    create_ticket(client, customer_a)
    assert client.get("/api/v1/analytics/overview", headers=auth(manager_a)).json()["open_tickets"] == 1
