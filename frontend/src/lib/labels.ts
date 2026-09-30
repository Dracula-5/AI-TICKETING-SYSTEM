import type { AIKind, AIStatus, Priority, Role, SlaStateName, TicketStatus } from "../api/types";

type Tone = "default" | "primary" | "info" | "success" | "warning" | "error" | "secondary";

export const STATUS: Record<TicketStatus, { label: string; tone: Tone }> = {
  submitted: { label: "Submitted", tone: "default" },
  triaged: { label: "Triaged", tone: "default" },
  assigned: { label: "Assigned", tone: "primary" },
  acknowledged: { label: "Acknowledged", tone: "primary" },
  in_progress: { label: "In progress", tone: "info" },
  waiting_for_customer: { label: "Waiting on requester", tone: "warning" },
  escalated: { label: "Escalated", tone: "error" },
  resolved: { label: "Resolved", tone: "success" },
  closed: { label: "Closed", tone: "default" },
  reopened: { label: "Reopened", tone: "secondary" },
};

// Verb used on the button that performs each transition.
export const TRANSITION_ACTION: Partial<Record<TicketStatus, string>> = {
  acknowledged: "Acknowledge",
  in_progress: "Start work",
  waiting_for_customer: "Ask requester",
  escalated: "Escalate",
  resolved: "Resolve",
  closed: "Close",
  reopened: "Reopen",
  triaged: "Mark triaged",
};

export const PRIORITY: Record<Priority, { label: string; tone: Tone }> = {
  critical: { label: "Critical", tone: "error" },
  high: { label: "High", tone: "warning" },
  medium: { label: "Medium", tone: "info" },
  low: { label: "Low", tone: "default" },
};
export const PRIORITIES: Priority[] = ["critical", "high", "medium", "low"];

export const SLA: Record<SlaStateName, { label: string; tone: Tone }> = {
  ok: { label: "On track", tone: "success" },
  at_risk: { label: "At risk", tone: "warning" },
  breached: { label: "Breached", tone: "error" },
  paused: { label: "Paused", tone: "default" },
  met: { label: "Met", tone: "success" },
  none: { label: "No SLA", tone: "default" },
};

export const ROLE: Record<Role, string> = {
  platform_admin: "Platform admin",
  org_admin: "Organization admin",
  manager: "Manager",
  agent: "Support agent",
  customer: "Requester",
  analyst: "Analyst (read-only)",
};
export const GRANTABLE_ROLES: Role[] = ["org_admin", "manager", "agent", "customer", "analyst"];

// Who made a triage/routing decision. Kept visually distinct everywhere so a
// rule, a person and (from P5) a model are never confused with each other.
export const DECISION_SOURCE = {
  rules: { label: "System rule", description: "Deterministic keyword rules and routing table" },
  manual: { label: "Human decision", description: "Set or changed by a person" },
  ai: { label: "AI recommendation", description: "Predicted by a model" },
} as const;

export const AI_KIND: Record<AIKind, string> = {
  category: "Category",
  priority: "Priority",
  team: "Team",
  assignee: "Assignee",
  duplicate: "Duplicate",
  resolution_time: "Expected resolution time",
  sla_risk: "SLA breach risk",
  next_action: "Next steps",
  summary: "Summary",
  reply: "Reply draft",
  request_info: "Ask the requester for details",
  escalate: "Escalate",
};

export const AI_SOURCE: Record<"ai" | "statistics" | "rules", string> = {
  ai: "AI model",
  statistics: "Statistics",
  rules: "System rule",
};

export const AI_STATUS: Record<AIStatus, { label: string; tone: Tone }> = {
  proposed: { label: "Suggested", tone: "default" },
  auto_applied: { label: "Applied automatically", tone: "secondary" },
  accepted: { label: "Accepted", tone: "success" },
  edited: { label: "Corrected", tone: "warning" },
  rejected: { label: "Rejected", tone: "default" },
  superseded: { label: "Superseded", tone: "default" },
  overridden: { label: "Overridden by a person", tone: "warning" },
  no_change: { label: "Agrees with current value", tone: "default" },
  invalid: { label: "Blocked by validation", tone: "error" },
  failed_verification: { label: "Rolled back", tone: "error" },
};

export const RISK_LABEL: Record<"low" | "medium" | "high", { label: string; tone: Tone; help: string }> = {
  low: { label: "Low risk", tone: "default", help: "Can be applied automatically if your organization enables it" },
  medium: { label: "Medium risk", tone: "warning", help: "Changes routing or SLA targets" },
  high: { label: "High risk", tone: "error", help: "Visible to the requester or changes the ticket's state — always needs a person" },
};
