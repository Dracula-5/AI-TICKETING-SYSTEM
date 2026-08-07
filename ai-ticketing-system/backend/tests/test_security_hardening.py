"""
Tests for Phase 3 security hardening: the image-URL validator, the
security-headers middleware, and rate-limit headroom sanity.
"""
import pytest
from pydantic import ValidationError

from app.schemas.products import ProductCreate
from tests.conftest import auth_headers


class TestImageUrlValidation:
    def test_rejects_javascript_scheme(self):
        with pytest.raises(ValidationError):
            ProductCreate(title="X", description="Y", price=10.0, image_urls=["javascript:alert(1)"])

    def test_rejects_bare_string(self):
        with pytest.raises(ValidationError):
            ProductCreate(title="X", description="Y", price=10.0, image_urls=["not-a-url"])

    def test_accepts_https_url(self):
        product = ProductCreate(title="X", description="Y", price=10.0, image_urls=["https://example.com/img.png"])
        assert product.image_urls == ["https://example.com/img.png"]

    def test_accepts_http_url(self):
        product = ProductCreate(title="X", description="Y", price=10.0, image_urls=["http://example.com/img.png"])
        assert product.image_urls == ["http://example.com/img.png"]

    def test_create_endpoint_rejects_bad_image_url(self, client, vendor_user, vendor):
        resp = client.post("/products/", json={
            "title": "Bad Image Product",
            "description": "x",
            "price": 100.0,
            "image_urls": ["javascript:alert(1)"],
        }, headers=auth_headers(vendor_user))
        assert resp.status_code == 422


class TestSecurityHeaders:
    def test_response_has_security_headers(self, client):
        resp = client.get("/health")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"


class TestRateLimitHeadroom:
    """
    The per-route limits (20/minute) must stay well above what a normal test
    run exercises against these endpoints, or the whole suite gets flaky.
    slowapi's default storage is per-process and persists for the life of
    the pytest run, so this is a real risk worth pinning explicitly.
    """

    def test_login_rate_limit_has_headroom(self, client, customer_user):
        for _ in range(5):
            resp = client.post(
                "/auth/login",
                data={"username": customer_user.email, "password": "wrong"},
            )
            assert resp.status_code != 429

    def test_register_simple_rate_limit_has_headroom(self, client):
        for i in range(3):
            resp = client.post("/auth/register-simple", json={
                "email": f"headroom-{i}@test.com",
                "password": "x",
            })
            assert resp.status_code != 429
