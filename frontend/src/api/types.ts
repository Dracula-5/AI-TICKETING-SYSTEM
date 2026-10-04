// Mirrors backend/app/schemas. Keep in sync when the API changes.

export interface DemoInfo {
  enabled: boolean;
  accounts: { role: Role; name: string; email: string; organization: string }[];
}

export type Role = "platform_admin" | "org_admin" | "manager" | "agent" | "customer" | "analyst";
export type Priority = "low" | "medium" | "high" | "critical";
export type TicketStatus =
  | "submitted"
  | "triaged"
  | "assigned"
  | "acknowledged"
  | "in_progress"
  | "waiting_for_customer"
  | "escalated"
  | "resolved"
  | "closed"
  | "reopened";
export type SlaStateName = "ok" | "at_risk" | "breached" | "paused" | "met" | "none";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface TokenOut {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface OrgSummary {
  id: number;
  name: string;
  slug: string;
  is_demo: boolean;
}

export interface UserOut {
  id: number;
  name: string;
  email: string;
  role: Role;
  tenant_id: number | null;
  is_active: boolean;
  email_verified_at: string | null;
  last_login_at: string | null;
  created_at: string;
}

export interface Me extends UserOut {
  organization: OrgSummary | null;
  permissions: string[];
  team_ids: number[];
}

export interface UserBrief {
  id: number;
  name: string;
  email: string;
  role: Role;
}

export interface TeamBrief {
  id: number;
  name: string;
}

export interface SlaState {
  first_response_due: string | null;
  first_responded_at: string | null;
  first_response_breached: boolean;
  resolution_due: string | null;
  resolution_breached: boolean;
  paused: boolean;
  state: SlaStateName;
}

export interface Ticket {
  id: number;
  number: number;
  title: string;
  description: string;
  priority: Priority;
  category: string | null;
  status: TicketStatus;
  channel: string;
  triage_source: "rules" | "manual" | "ai" | null;
  requester: UserBrief;
  assignee: UserBrief | null;
  team: TeamBrief | null;
  sla: SlaState;
  acknowledged_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  reopened_count: number;
  resolution_summary: string | null;
  data_origin: string;
  created_at: string;
  updated_at: string;
}

export interface TicketDetail extends Ticket {
  allowed_transitions: TicketStatus[];
  can_assign: boolean;
  can_edit: boolean;
}

export interface StatusHistoryEntry {
  id: number;
  from_status: TicketStatus | null;
  to_status: TicketStatus;
  actor_type: "user" | "system" | "ai";
  actor: UserBrief | null;
  reason: string | null;
  created_at: string;
}

export interface Attachment {
  id: number;
  ticket_id: number;
  comment_id: number | null;
  filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_by: UserBrief;
  created_at: string;
}

export interface Comment {
  id: number;
  ticket_id: number;
  visibility: "public" | "internal";
  content: string;
  author: UserBrief | null;
  attachments: Attachment[];
  created_at: string;
}

export interface Team {
  id: number;
  name: string;
  description: string | null;
  member_ids: number[];
}

export interface Category {
  id: number;
  name: string;
  description: string | null;
  keywords: string[];
  default_team_id: number | null;
  is_active: boolean;
}

export interface SlaPolicy {
  priority: Priority;
  first_response_minutes: number;
  resolution_minutes: number;
}

export interface OrgSettings {
  auto_assign: boolean;
  auto_close_days: number;
  reopen_window_days: number;
  portal_signup_enabled: boolean;
  portal_allowed_domains: string[];
  ai_auto_apply_kinds: ("category" | "priority" | "team" | "assignee")[];
  ai_auto_apply_threshold: number;
  ai_duplicate_threshold: number;
  ai_min_history: number;
  ai_llm_monthly_token_budget: number;
}

export interface Organization {
  id: number;
  name: string;
  slug: string;
  is_demo: boolean;
  settings: OrgSettings;
  created_at: string;
}

export interface Invitation {
  id: number;
  email: string;
  role: Role;
  team_id: number | null;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
  invite_url?: string;
}

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  message: string | null;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

export interface CountItem {
  key: string | null;
  count: number;
}

export interface WorkloadItem {
  id: number | null;
  name: string;
  open: number;
}

export interface Overview {
  generated_at: string;
  data_origin: string;
  open_tickets: number;
  created_today: number;
  unassigned_open: number;
  sla_breached_open: number;
  sla_at_risk_open: number;
  resolved_last_30d: number;
  avg_first_response_minutes_30d: number | null;
  avg_resolution_hours_30d: number | null;
  sla_compliance_pct_30d: number | null;
  reopen_rate_pct_30d: number | null;
  by_status: CountItem[];
  by_priority: CountItem[];
  by_category: CountItem[];
  by_team: WorkloadItem[];
  by_agent: WorkloadItem[];
  trend_14d: { day: string; created: number; resolved: number }[];
}

export interface AuditEntry {
  id: number;
  actor_type: string;
  actor_name: string | null;
  actor_email: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  changes: Record<string, unknown> | null;
  ip: string | null;
  request_id: string | null;
  created_at: string;
}

// --- AI recommendations -------------------------------------------------------
export type AIKind =
  | "category"
  | "priority"
  | "team"
  | "assignee"
  | "duplicate"
  | "resolution_time"
  | "sla_risk"
  | "next_action"
  | "summary"
  | "reply"
  | "request_info"
  | "escalate";

export type AIStatus =
  | "proposed"
  | "auto_applied"
  | "accepted"
  | "edited"
  | "rejected"
  | "superseded"
  | "overridden"
  | "no_change"
  | "invalid"
  | "failed_verification";

export interface SimilarTicket {
  ticket_id: number;
  number: number;
  title: string;
  status: TicketStatus;
  similarity: number;
  same_requester?: boolean;
}

export interface AIPrediction {
  id: number;
  kind: AIKind;
  source: "ai" | "rules" | "statistics";
  model: string;
  model_version: string;
  value: Record<string, unknown>;
  confidence: number | null;
  evidence: {
    similar_tickets?: SimilarTicket[];
    candidates?: SimilarTicket[];
    distribution?: Record<string, number>;
    neighbors_used?: number;
    policy?: string;
    method?: string;
    reason?: string;
    n?: number;
    threshold?: number;
    llm_call_id?: number;
  } | null;
  latency_ms: number | null;
  status: AIStatus;
  final_value: Record<string, unknown> | null;
  decided_at: string | null;
  created_at: string;
}

export interface TicketAI {
  status: "disabled" | "pending" | "ready" | "failed";
  model: string | null;
  predictions: AIPrediction[];
}

export interface AIKindStats {
  kind: AIKind;
  total: number;
  auto_applied: number;
  accepted: number;
  edited: number;
  rejected: number;
  overridden: number;
  pending: number;
  no_change: number;
  invalid: number;
  failed_verification: number;
  acceptance_rate: number | null;
  override_rate: number | null;
  automation_false_positive_rate: number | null;
  mean_confidence: number | null;
}

export interface AICapabilities {
  triage: boolean;
  embedding_model: string | null;
  text_generation: boolean;
  llm_provider: string | null;
  llm_model: string | null;
}

export interface LLMUsage {
  calls: number;
  failed_calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  p50_latency_ms: number | null;
  tokens_this_month: number;
  monthly_token_budget: number;
}

export interface AIPerformance {
  window_days: number;
  data_origin: string;
  tickets_analyzed: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  models: Record<string, number>;
  by_kind: AIKindStats[];
  text_generation: LLMUsage;
  definitions: Record<string, string>;
}

// --- knowledge base -----------------------------------------------------------
export interface KBDocument {
  id: number;
  title: string;
  filename: string;
  content_type: string;
  visibility: "internal" | "public";
  status: "processing" | "ready" | "failed";
  error: string | null;
  size_bytes: number;
  chunk_count: number;
  data_origin: string;
  created_at: string;
  updated_at: string;
}

export interface KBDocumentDetail extends KBDocument {
  text: string | null;
}

export interface KBHit {
  chunk_id: number;
  document_id: number;
  title: string;
  heading: string | null;
  snippet: string;
  visibility: "internal" | "public";
  score: number;
  dense_similarity: number | null;
  reranked: boolean;
}

export interface KBSearch {
  query_id: number | null;
  mode: string;
  hits: KBHit[];
}

export interface KBCitation {
  number: number;
  chunk_id: number;
  document_id: number;
  title: string;
  heading: string | null;
  snippet: string;
}

export interface KBAnswer {
  query_id: number | null;
  status: "answered" | "no_answer" | "search_only";
  answer: string | null;
  citations: KBCitation[];
  supported_ratio: number | null;
  unsupported_sentences: string[];
  mode: string;
  hits: KBHit[];
}

export interface AgentRun {
  id: number;
  trigger: string;
  planner: string;
  model: string;
  status: string;
  steps: { kind: AIKind; tool: string | null; outcome: string; reason?: string; risk?: string; confidence: number | null; ms?: number }[];
  latency_ms: number | null;
  created_at: string;
}

export interface QueueItem {
  prediction: AIPrediction;
  risk: "low" | "medium" | "high";
  ticket_id: number;
  ticket_number: number;
  ticket_title: string;
  ticket_status: TicketStatus;
  ticket_priority: Priority;
}

export interface ApprovalQueue {
  items: QueueItem[];
  total: number;
  by_risk: Record<string, number>;
}

export interface AIMonitoringRun {
  status: "ok" | "alert" | "insufficient_data";
  metrics: {
    recent_tickets: number;
    baseline_tickets: number;
    category_psi?: number;
    embedding_centroid_distance?: number;
    novelty_rate?: number;
    acceptance_recent?: number | null;
    acceptance_baseline?: number | null;
  };
  alerts: string[];
  engine_version: string;
  created_at: string;
}
