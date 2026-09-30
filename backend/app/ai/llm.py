"""
LLM provider interface (ADR-11): one small `complete()` call behind which the
provider can change, and a ledger row (`llm_calls`) for every call — tokens,
latency, outcome and, when prices are configured, cost.

Nothing is enabled implicitly. LLM features need LLM_PROVIDER (anthropic |
openai) *and* LLM_API_KEY; a key merely present in the environment under a
provider's own variable name (e.g. OPENAI_API_KEY) is ignored on purpose, so
ticket text is never sent to a third party without an explicit decision.

Prices are configuration (LLM_PRICE_INPUT_PER_MTOK / LLM_PRICE_OUTPUT_PER_MTOK,
USD per million tokens, from the provider's price list). If they are unset,
cost is recorded as unknown rather than guessed.
"""

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import settings
from app.db.database import utcnow
from app.db.models import LLMCall

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(45.0, connect=10.0)
RETRY_STATUS = {429, 500, 502, 503, 504, 529}


class LLMError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, max_tokens: int) -> Completion: ...


def _post(url: str, headers: dict, body: dict) -> dict:
    last: Exception | None = None
    for attempt in range(3):
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            last = e
        else:
            if r.status_code < 400:
                return r.json()
            if r.status_code not in RETRY_STATUS:
                raise LLMError(f"LLM provider returned {r.status_code}")
            last = LLMError(f"LLM provider returned {r.status_code}")
        time.sleep(0.5 * 2**attempt)
    raise LLMError(f"LLM provider unavailable: {last}")


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, api_key: str):
        self.model, self._key = model, api_key

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": self._key, "anthropic-version": "2023-06-01"},
            {
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        usage = data.get("usage", {})
        return Completion(text.strip(), int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)))


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, api_key: str):
        self.model, self._key = model, api_key

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        data = _post(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {self._key}"},
            {
                "model": self.model,
                "max_completion_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
        )
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage", {})
        return Completion(
            (choice.get("message", {}).get("content") or "").strip(),
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
        )


def get_llm() -> Provider | None:
    if settings.llm_provider == "none" or not settings.llm_api_key or not settings.llm_model:
        return None
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.llm_model, settings.llm_api_key)
    return OpenAIProvider(settings.llm_model, settings.llm_api_key)


def cost_usd(input_tokens: int, output_tokens: int) -> float | None:
    pin, pout = settings.llm_price_input_per_mtok, settings.llm_price_output_per_mtok
    if pin is None or pout is None:
        return None
    return round((input_tokens * pin + output_tokens * pout) / 1_000_000, 6)


def tokens_used_this_month(db: Session, tenant_id: int, now: datetime | None = None) -> int:
    now = now or utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = (
        db.query(func.coalesce(func.sum(LLMCall.input_tokens + LLMCall.output_tokens), 0))
        .filter(LLMCall.tenant_id == tenant_id, LLMCall.created_at >= start)
        .scalar()
    )
    return int(used or 0)


def call(
    db: Session,
    provider: Provider,
    *,
    tenant_id: int,
    feature: str,
    system: str,
    user: str,
    max_tokens: int,
    budget_tokens: int,
    ticket_id: int | None = None,
    user_id: int | None = None,
) -> tuple[Completion, LLMCall]:
    """Budget check → provider call → ledger row (success or failure)."""
    if tokens_used_this_month(db, tenant_id) >= budget_tokens:
        raise LLMError("This organization's monthly AI text-generation budget is used up", 429)
    row = LLMCall(
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        user_id=user_id,
        feature=feature,
        provider=provider.name,
        model=provider.model,
        prompt_sha256=hashlib.sha256((system + "\x00" + user).encode()).hexdigest(),
    )
    started = time.perf_counter()
    try:
        out = provider.complete(system, user, max_tokens)
    except LLMError as e:
        row.status, row.error = "error", e.message[:500]
        metrics.LLM_CALLS.labels(feature, "error").inc()
        row.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        db.add(row)
        db.flush()
        raise
    row.latency_ms = round((time.perf_counter() - started) * 1000, 1)
    row.input_tokens, row.output_tokens = out.input_tokens, out.output_tokens
    row.cost_usd = cost_usd(out.input_tokens, out.output_tokens)
    row.status = "ok" if out.text else "empty"
    metrics.LLM_CALLS.labels(feature, row.status).inc()
    metrics.LLM_TOKENS.labels(feature, "input").inc(out.input_tokens)
    metrics.LLM_TOKENS.labels(feature, "output").inc(out.output_tokens)
    db.add(row)
    db.flush()
    if not out.text:
        raise LLMError("The model returned no text")
    logger.info(
        "llm_call",
        extra={
            "feature": feature,
            "model": provider.model,
            "latency_ms": row.latency_ms,
            "input_tokens": out.input_tokens,
            "output_tokens": out.output_tokens,
        },
    )
    return out, row
