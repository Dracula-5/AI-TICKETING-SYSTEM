"""
Thin Redis caching wrapper. The cache is always an optimization, never a hard
dependency: if Redis is unreachable, every call degrades to a silent no-op
(callers just get a cache miss) after logging exactly one warning per process
lifetime — no per-request timeout cost and no way for a cache outage to take
the API down with it.
"""
import json
import logging

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# None = not yet attempted, False = known unavailable, else = a live client.
_client: "redis.Redis | bool | None" = None


def _get_client():
    global _client
    if _client is False:
        return None
    if _client is None:
        try:
            candidate = redis.Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
                decode_responses=True,
            )
            candidate.ping()
            _client = candidate
        except Exception:
            logger.warning("Redis unavailable at %s - running without caching", settings.redis_url)
            _client = False
            return None
    return _client


def cache_get(key: str) -> dict | None:
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_set(key: str, value: dict, ttl: int) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value), ex=ttl)
    except Exception:
        pass
