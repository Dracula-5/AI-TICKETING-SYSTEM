"""
Shared slowapi Limiter. Lives in its own module so routers can apply per-route
limits (e.g. @limiter.limit("20/minute") on login) without importing main.py.

Keyed by client address. Behind the reverse proxy, uvicorn runs with
--proxy-headers so request.client is the real client, not the proxy. Storage
is per-process memory for now; moving it to Redis (shared across processes)
is part of P2.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])
