"""
Security regression tests. The TestAuditFindings class maps one-to-one to
the defects A1–A10 reproduced in docs/current_architecture.md §5.
"""

import pytest

from app.core.config import Settings, settings
from app.core.limiter import limiter
from app.db.models import User
from tests.conftest import PASSWORD, auth, create_ticket, move

API = "/api/v1"


class TestAuditFindings:
    def test_a1_a2_registration_cannot_pick_role_or_tenant(self, client, db, org_a):
        client.post(
            f"{API}/auth/register",
            json={
                "name": "Mallory",
                "email": "mallory@evil.example.com",
                "password": "Str0ng-Passw0rd",
                "organization_name": "Evil",
                "role": "org_admin",
                "tenant_id": org_a.id,
            },
        )
        user = db.query(User).filter(User.email == "mallory@evil.example.com").one()
        assert user.tenant_id != org_a.id

    @pytest.mark.parametrize(
        "method,path",
        [
            ("post", "/users/"),
            ("post", "/tenants/"),
            ("get", "/tenants/1"),
            ("put", "/sla/check"),
            ("get", "/api/v1/metrics"),
            ("post", "/auth/register-simple"),
            ("post", "/users/create-default-users"),
        ],
    )
    def test_a3_to_a6_legacy_unauthenticated_endpoints_are_gone(self, client, method, path):
        for prefix in ("", API):
            kwargs = {"json": {}} if method != "get" else {}
            resp = getattr(client, method)(prefix + path, **kwargs)
            assert resp.status_code in (404, 405), (prefix + path, resp.status_code)

    def test_a5_metrics_carry_no_tenant_data_and_need_a_token(self, client, db, org_a, customer_a, monkeypatch):
        # The legacy /metrics leaked per-tenant business data to anyone. Its
        # replacement is Prometheus operational counters only, token-protected.
        create_ticket(client, customer_a, title="Payroll for Acme is wrong")
        body = client.get("/metrics").text
        assert "Acme" not in body and "Payroll" not in body and org_a.slug not in body
        monkeypatch.setattr(settings, "metrics_token", "s" * 32)
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer " + "s" * 32}).status_code == 200

    def test_a7_no_default_credentials_are_seeded(self, client, db):
        assert db.query(User).count() == 0
        resp = client.post(f"{API}/auth/login", data={"username": "admin@gmail.com", "password": "admin123"})
        assert resp.status_code == 401

    def test_a8_a9_intra_tenant_idor(self, client, customer_a, customer_a2):
        tid = create_ticket(client, customer_a)["id"]
        assert client.get(f"{API}/tickets/{tid}", headers=auth(customer_a2)).status_code == 404
        assert move(client, customer_a2, tid, "closed", reason="x").status_code == 404

    def test_a10_transitions_are_validated_and_recorded(self, client, manager_a, customer_a):
        tid = create_ticket(client, customer_a)["id"]
        assert move(client, manager_a, tid, "closed", reason="Duplicate").status_code == 200
        # closed -> open is not a state; closed -> triaged is not a legal edge.
        assert move(client, manager_a, tid, "open").status_code == 422
        assert move(client, manager_a, tid, "triaged").status_code == 409
        history = client.get(f"{API}/tickets/{tid}/history", headers=auth(manager_a)).json()
        assert history[-1]["to_status"] == "closed" and history[-1]["reason"] == "Duplicate"
        assert history[-1]["actor"]["id"] == manager_a.id


class TestHeaders:
    def test_security_headers_and_request_id(self, client):
        resp = client.get("/health")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert resp.headers["content-security-policy"].startswith("default-src 'none'")
        assert len(resp.headers["x-request-id"]) >= 8

    def test_incoming_request_id_is_echoed_only_if_safe(self, client):
        assert client.get("/health", headers={"X-Request-ID": "abc-12345678"}).headers["x-request-id"] == "abc-12345678"
        injected = client.get("/health", headers={"X-Request-ID": "bad\r\nvalue"}).headers["x-request-id"]
        assert injected != "bad\r\nvalue"

    def test_cors_allows_only_configured_origins(self, client):
        ok = client.options(
            f"{API}/auth/login", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
        )
        assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
        bad = client.options(
            f"{API}/auth/login", headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"}
        )
        assert "access-control-allow-origin" not in bad.headers

    def test_refresh_cookie_is_http_only_and_scoped(self, client, agent_a):
        resp = client.post(f"{API}/auth/login", data={"username": agent_a.email, "password": PASSWORD})
        cookie = resp.headers["set-cookie"].lower()
        assert "httponly" in cookie and "path=/api/v1/auth" in cookie and "samesite=lax" in cookie

    def test_errors_do_not_leak_stack_traces(self, client, agent_a, monkeypatch):
        import app.routers.tickets as tickets_router

        def boom(*a, **k):
            raise RuntimeError("secret internals")

        monkeypatch.setattr(tickets_router.svc, "visible_tickets_query", boom)
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get(f"{API}/tickets", headers=auth(agent_a))
        assert resp.status_code == 500 and "secret" not in resp.text


class TestRateLimiting:
    def test_login_is_rate_limited(self, client, agent_a):
        limiter.enabled = True
        codes = [
            client.post(f"{API}/auth/login", data={"username": agent_a.email, "password": "x"}).status_code
            for _ in range(21)
        ]
        assert codes[:20] == [401] * 20 and codes[20] == 429


class TestProductionConfig:
    def _prod(self, **overrides):
        base = dict(
            environment="production",
            secret_key="x" * 40,
            cookie_secure=True,
            database_url="postgresql://u:p@db/nexadesk",
            bcrypt_rounds=12,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            metrics_token="m" * 32,
        )
        return Settings(**{**base, **overrides})

    def test_valid_production_config_passes(self):
        self._prod().validate_for_environment()

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("postgres://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
            ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
            ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
            ("sqlite:///./x.db", "sqlite:///./x.db"),
        ],
    )
    def test_hosted_database_urls_use_the_installed_driver(self, url, expected):
        assert Settings(database_url=url).database_url == expected

    @pytest.mark.parametrize(
        "override,message",
        [
            ({"secret_key": "dev-only-insecure-secret-key-change-me-before-deploying"}, "SECRET_KEY"),
            ({"secret_key": "short"}, "SECRET_KEY"),
            ({"cookie_secure": False}, "COOKIE_SECURE"),
            ({"database_url": "sqlite:///./x.db"}, "PostgreSQL"),
            ({"bcrypt_rounds": 4}, "BCRYPT_ROUNDS"),
            ({"embedding_model": "test-hashing"}, "EMBEDDING_MODEL"),
            ({"metrics_token": ""}, "METRICS_TOKEN"),
        ],
    )
    def test_unsafe_production_config_refuses_to_boot(self, override, message):
        with pytest.raises(RuntimeError, match=message):
            self._prod(**override).validate_for_environment()

    def test_dev_router_not_mounted_outside_dev(self):
        # Mounted in this test process (ENVIRONMENT=test), guarded by environment in main.py.
        import inspect

        import app.main as main

        assert 'settings.environment in ("development", "test")' in inspect.getsource(main)
