"""
Error monitoring (Sentry-compatible). A no-op unless SENTRY_DSN is set.

Privacy: no PII is sent (send_default_pii=False), request bodies are never
attached, and Authorization/Cookie headers are scrubbed before an event leaves
the process. Performance tracing is off — metrics come from P12's
Prometheus stack, not from sampled traces.
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_SCRUB_HEADERS = {"authorization", "cookie", "set-cookie", "x-api-key"}


def _scrub(event: dict, _hint: dict) -> dict:
    request = event.get("request") or {}
    headers = request.get("headers") or {}
    for key in list(headers):
        if key.lower() in _SCRUB_HEADERS:
            headers[key] = "[scrubbed]"
    request.pop("data", None)
    request.pop("cookies", None)
    return event


def init_error_monitoring(component: str) -> bool:
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.release,
        send_default_pii=False,
        traces_sample_rate=0.0,
        max_request_body_size="never",
        before_send=_scrub,  # type: ignore[arg-type]
    )
    sentry_sdk.set_tag("component", component)
    logger.info("error_monitoring_enabled", extra={"component": component})
    return True
