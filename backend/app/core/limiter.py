"""
Shared slowapi Limiter. Lives in its own module so routers can apply per-route
limits (e.g. @limiter.limit("20/minute") on login) without importing main.py.

Keyed by client address. Behind the reverse proxy, uvicorn runs with
--proxy-headers so request.client is the real client, not the proxy.

Counters live in RATE_LIMIT_STORAGE_URI: memory:// (one process) or a redis://
URL shared by every API process. If the store is unreachable the limiter fails
open (swallow_errors) — an availability-over-strictness choice recorded in
docs/security.md; the outage is logged.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default],
    storage_uri=settings.rate_limit_storage_uri,
    swallow_errors=not settings.rate_limit_storage_uri.startswith("memory"),
)
