"""
Cross-process real-time fan-out over Redis pub/sub.

Any process — an API worker handling a request, or the background worker
recording an SLA breach — publishes {user_id, payload} to one channel. Every
API process subscribes and forwards the message to the WebSocket connections
it holds (NotificationConnectionManager). This is what makes live
notifications correct with several API processes and a separate worker.

Without Redis (tests, single-process development) publish() returns False and
the caller pushes to the local connection manager directly.
"""

import asyncio
import json
import logging

from app.core.cache import get_redis
from app.core.config import settings
from app.services.notification_ws import NotificationConnectionManager

logger = logging.getLogger(__name__)

CHANNEL = "nexadesk:realtime"
RECONNECT_SECONDS = 5


def publish(user_id: int, payload: dict) -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        client.publish(CHANNEL, json.dumps({"user_id": user_id, "payload": payload}))
        return True
    except Exception:
        logger.warning("realtime_publish_failed", extra={"user_id": user_id})
        return False


async def dispatch(manager: NotificationConnectionManager, raw: str) -> None:
    message = json.loads(raw)
    await manager.send_to_user(int(message["user_id"]), message["payload"])


async def run_subscriber(manager: NotificationConnectionManager) -> None:
    """Long-running task started by the API lifespan; reconnects on failure."""
    import redis.asyncio as aioredis

    while True:
        client = None
        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(CHANNEL)
            logger.info("realtime_subscriber_connected")
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    try:
                        await dispatch(manager, message["data"])
                    except Exception:
                        logger.exception("realtime_dispatch_failed")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("realtime_subscriber_disconnected; retrying in %ss", RECONNECT_SECONDS)
            await asyncio.sleep(RECONNECT_SECONDS)
        finally:
            if client is not None:
                await client.aclose()
