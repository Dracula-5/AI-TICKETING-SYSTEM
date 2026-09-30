"""
Human-in-the-loop policy: which AI suggestions may change a ticket without a
person approving them.

Risk classes (fixed in code — an organization can only be *more* cautious):

    low     category                          -> may auto-apply when enabled
    medium  priority, team, assignee          -> may auto-apply when enabled per kind
    high    duplicate (closing/merging),      -> never auto-applied; always a
            customer-facing replies              recommendation for a person
    info    summary, sla_risk, resolution_time, next_action -> informational only

Organization settings: `ai_auto_apply_kinds` (subset of AUTO_APPLICABLE,
default empty = recommend only) and `ai_auto_apply_threshold` (default 0.9).
Anything below the threshold stays a recommendation; "unknown" (no confidence)
is never auto-applied.
"""

from dataclasses import dataclass

from app.db.models import Tenant
from app.services.organizations import org_setting

RISK = {
    "category": "low",
    "priority": "medium",
    "team": "medium",
    "assignee": "medium",
    "duplicate": "high",
    "reply": "high",
    "request_info": "high",
    "escalate": "high",
    "summary": "info",
    "sla_risk": "info",
    "resolution_time": "info",
    "next_action": "info",
}
AUTO_APPLICABLE = frozenset({"category", "priority", "team", "assignee"})


@dataclass(frozen=True)
class Decision:
    auto_apply: bool
    reason: str


def decide(tenant: Tenant, kind: str, confidence: float | None) -> Decision:
    risk = RISK.get(kind, "high")
    if risk == "info":
        return Decision(False, "informational")
    if risk == "high" or kind not in AUTO_APPLICABLE:
        return Decision(False, "high-risk action: requires a person")
    enabled = set(org_setting(tenant, "ai_auto_apply_kinds")) & AUTO_APPLICABLE
    if kind not in enabled:
        return Decision(False, "auto-apply not enabled for this kind")
    if confidence is None:
        return Decision(False, "no confidence estimate")
    threshold = float(org_setting(tenant, "ai_auto_apply_threshold"))
    if confidence < threshold:
        return Decision(False, f"confidence {confidence:.2f} below threshold {threshold:.2f}")
    return Decision(True, f"confidence {confidence:.2f} ≥ threshold {threshold:.2f}")
