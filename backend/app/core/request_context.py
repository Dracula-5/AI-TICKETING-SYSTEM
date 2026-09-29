"""
Per-request context (request id, client address, user agent) carried in
contextvars so the audit log and structured logs can attach it without every
function taking a Request parameter.
"""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    request_id: str | None = None
    ip: str | None = None
    user_agent: str | None = None


_EMPTY = RequestContext()
# RequestContext is a frozen dataclass, so sharing one default instance is safe.
_ctx: ContextVar[RequestContext] = ContextVar("request_context", default=_EMPTY)  # noqa: B039


def set_request_context(ctx: RequestContext):
    return _ctx.set(ctx)


def reset_request_context(token) -> None:
    _ctx.reset(token)


def get_request_context() -> RequestContext:
    return _ctx.get()
