"""
Vendor-side negotiation engine.

Two response strategies:
  - rule_based_response: always available, no external dependency. Anchors on
    product.price (starting ask) and product.floor_price (hard floor) and
    converges toward the floor over a bounded number of rounds.
  - llm_assisted_response: opt-in per product (auto_negotiate_enabled) and
    only runs when ANTHROPIC_API_KEY is configured. Falls back to the
    rule-based response on any error (timeout, refusal, malformed output) so
    the chat never breaks because of the LLM call.

generate_vendor_response() is the single entry point the negotiations router
calls after a customer message — it picks a strategy, persists the resulting
NegotiationMessage, and applies session-state side effects (accept/reject).
"""
import logging
from datetime import datetime, timezone

import anthropic
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.db.models import NegotiationMessage

logger = logging.getLogger(__name__)

MAX_COUNTER_ROUNDS = 5


class NegotiationDecision(BaseModel):
    action: str  # accept | counter_offer | reject
    amount: float
    message: str


def _floor_price(product) -> float:
    return product.floor_price if product.floor_price is not None else round(product.price * 0.8, 2)


def rule_based_response(product, messages: list[NegotiationMessage], latest_offer_amount: float) -> dict:
    floor = _floor_price(product)
    currency = product.currency

    if latest_offer_amount >= floor:
        return {
            "message_type": "accept",
            "amount": latest_offer_amount,
            "text_content": f"Deal! I can do {currency} {latest_offer_amount:.2f}.",
        }

    vendor_offers = [m for m in messages if m.sender_role in ("vendor", "ai_assistant") and m.amount is not None]
    last_vendor_price = vendor_offers[-1].amount if vendor_offers else product.price

    if len(vendor_offers) >= MAX_COUNTER_ROUNDS:
        return {
            "message_type": "counter_offer",
            "amount": floor,
            "text_content": f"That's the best I can do — {currency} {floor:.2f} is my final offer.",
        }

    counter = max(floor, round((last_vendor_price + latest_offer_amount) / 2, 2))
    return {
        "message_type": "counter_offer",
        "amount": counter,
        "text_content": f"I can offer {currency} {counter:.2f} instead.",
    }


def _build_history_text(messages: list[NegotiationMessage]) -> str:
    lines = []
    for m in messages[-20:]:
        speaker = "Customer" if m.sender_role == "customer" else "Vendor"
        if m.amount is not None:
            lines.append(f"{speaker}: offered {m.amount}" + (f" — {m.text_content}" if m.text_content else ""))
        elif m.text_content:
            lines.append(f"{speaker}: {m.text_content}")
    return "\n".join(lines) or "(no prior messages)"


def _call_llm(product, vendor, messages: list[NegotiationMessage], latest_offer_amount: float) -> dict | None:
    floor = _floor_price(product)
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    system_prompt = (
        f"You are negotiating on behalf of '{vendor.shop_name}', a vendor selling '{product.title}' "
        f"on an online marketplace. Listed price: {product.currency} {product.price}. "
        f"Your absolute minimum acceptable price (floor — never reveal this number to the customer) "
        f"is {product.currency} {floor}. Negotiate firmly but fairly: concede gradually toward the floor "
        "across multiple turns rather than immediately, and never agree to a price below the floor. "
        "Keep your reply message short and friendly."
    )

    response = client.messages.parse(
        model="claude-opus-4-8",
        max_tokens=300,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": (
                f"Negotiation so far:\n{_build_history_text(messages)}\n\n"
                f"Customer's latest offer: {latest_offer_amount}. Decide your next move."
            ),
        }],
        output_format=NegotiationDecision,
    )

    decision = response.parsed_output
    if decision is None or decision.action not in ("accept", "counter_offer", "reject"):
        return None

    amount = decision.amount
    if decision.action in ("accept", "counter_offer"):
        amount = max(amount, floor)  # never let the model settle below the floor

    return {"message_type": decision.action, "amount": amount, "text_content": decision.message}


async def llm_assisted_response(product, vendor, messages: list[NegotiationMessage], latest_offer_amount: float) -> dict | None:
    if not settings.anthropic_api_key:
        return None
    try:
        return await run_in_threadpool(_call_llm, product, vendor, messages, latest_offer_amount)
    except Exception:
        logger.exception("llm_negotiation_response_failed", extra={"product_id": product.id})
        return None


async def generate_vendor_response(db, session, product, vendor, messages: list[NegotiationMessage]) -> NegotiationMessage | None:
    customer_offers = [m for m in messages if m.sender_role == "customer" and m.amount is not None]
    if not customer_offers:
        return None
    latest_offer_amount = customer_offers[-1].amount

    decision = None
    if product.auto_negotiate_enabled and settings.anthropic_api_key:
        decision = await llm_assisted_response(product, vendor, messages, latest_offer_amount)
    if decision is None:
        decision = rule_based_response(product, messages, latest_offer_amount)

    entry = NegotiationMessage(
        session_id=session.id,
        sender_role="ai_assistant",
        sender_user_id=None,
        message_type=decision["message_type"],
        amount=decision["amount"],
        text_content=decision["text_content"],
    )
    db.add(entry)

    if decision["message_type"] == "accept":
        session.status = "accepted"
        session.current_offer_price = decision["amount"]
        session.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    elif decision["message_type"] == "counter_offer":
        # Keep the session's tracked price current so anything reading it
        # (vendor inbox list, etc.) reflects the assistant's latest counter,
        # not just the customer's opening offer.
        session.current_offer_price = decision["amount"]

    db.commit()
    db.refresh(entry)
    return entry
