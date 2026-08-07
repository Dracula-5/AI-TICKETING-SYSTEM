"""
Tests for the Redis caching wrapper (app/core/cache.py). Uses a small
in-memory fake client — no real Redis server, no new test dependency — to
exercise cache_get/cache_set logic, plus confirms the app degrades
gracefully when Redis is unreachable (the default in this test environment).
"""
import app.core.cache as cache_module
from app.core.cache import cache_get, cache_set
from tests.conftest import auth_headers


class FakeRedisClient:
    def __init__(self):
        self.store = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value


class BrokenRedisClient:
    def get(self, key):
        raise ConnectionError("boom")

    def set(self, key, value, ex=None):
        raise ConnectionError("boom")


class TestCacheWrapper:
    def test_set_then_get_round_trips_json(self, monkeypatch):
        monkeypatch.setattr(cache_module, "_client", FakeRedisClient())
        cache_set("mykey", {"a": 1, "b": [1, 2, 3]}, ttl=30)
        assert cache_get("mykey") == {"a": 1, "b": [1, 2, 3]}

    def test_get_miss_returns_none(self, monkeypatch):
        monkeypatch.setattr(cache_module, "_client", FakeRedisClient())
        assert cache_get("does-not-exist") is None

    def test_known_unavailable_short_circuits(self, monkeypatch):
        # _client = False means "already tried once, Redis is down" --
        # cache_get/cache_set must no-op without attempting a connection.
        monkeypatch.setattr(cache_module, "_client", False)
        cache_set("k", {"x": 1}, ttl=10)  # must not raise
        assert cache_get("k") is None

    def test_broken_client_degrades_gracefully(self, monkeypatch):
        monkeypatch.setattr(cache_module, "_client", BrokenRedisClient())
        assert cache_get("k") is None
        cache_set("k", {"x": 1}, ttl=10)  # must not raise


class TestProductListingCacheIntegration:
    def test_marketplace_listing_works_without_redis(self, client, customer_user, vendor, product):
        # No Redis server runs in this test environment -- this pins the
        # graceful-degradation path explicitly rather than relying on it
        # being incidentally exercised by the rest of the product suite.
        resp = client.get("/products/", headers=auth_headers(customer_user))
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_cached_listing_served_from_cache(self, client, customer_user, vendor, product, monkeypatch):
        fake = FakeRedisClient()
        monkeypatch.setattr(cache_module, "_client", fake)

        first = client.get("/products/", headers=auth_headers(customer_user))
        assert first.status_code == 200
        assert len(fake.store) == 1  # first request populated the cache

        # Mutate the store directly to prove the second response comes from
        # cache rather than a fresh query.
        cached_key = next(iter(fake.store))
        cache_get_result = cache_get(cached_key)
        cache_get_result["total"] = 999999
        cache_set(cached_key, cache_get_result, ttl=30)

        second = client.get("/products/", headers=auth_headers(customer_user))
        assert second.json()["total"] == 999999
