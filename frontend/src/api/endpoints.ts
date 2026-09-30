import { api } from "./client";
import type {
  AgentRun,
  AICapabilities,
  AIMonitoringRun,
  AIPerformance,
  AIPrediction,
  ApprovalQueue,
  AuditEntry,
  Attachment,
  Category,
  Comment,
  Invitation,
  KBAnswer,
  KBDocument,
  KBDocumentDetail,
  KBSearch,
  Me,
  NotificationItem,
  Organization,
  OrgSettings,
  Overview,
  Page,
  Priority,
  Role,
  SlaPolicy,
  StatusHistoryEntry,
  Team,
  Ticket,
  TicketAI,
  TicketDetail,
  TicketStatus,
  TokenOut,
  UserOut,
} from "./types";

const data = <T,>(p: Promise<{ data: T }>) => p.then((r) => r.data);

// --- auth -----------------------------------------------------------------
export const authApi = {
  login: (email: string, password: string) =>
    data<TokenOut>(
      api.post("/auth/login", new URLSearchParams({ username: email, password }), {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      }),
    ),
  register: (body: { name: string; email: string; password: string; organization_name?: string; join_slug?: string }) =>
    data<TokenOut>(api.post("/auth/register", body)),
  logout: () => data(api.post("/auth/logout")),
  me: () => data<Me>(api.get("/auth/me")),
  verifyEmail: (token: string) => data(api.post("/auth/verify-email", { token })),
  resendVerification: () => data(api.post("/auth/resend-verification")),
  forgotPassword: (email: string) => data(api.post("/auth/forgot-password", { email })),
  resetPassword: (token: string, new_password: string) => data(api.post("/auth/reset-password", { token, new_password })),
  previewInvitation: (token: string) =>
    data<{ organization_name: string; email: string; role: Role; invited_by: string }>(
      api.get(`/auth/invitations/${encodeURIComponent(token)}`),
    ),
  acceptInvitation: (token: string, name: string, password: string) =>
    data<TokenOut>(api.post("/auth/accept-invitation", { token, name, password })),
  portalInfo: (slug: string) =>
    data<{ name: string; slug: string; signup_enabled: boolean; allowed_domains: string[] }>(
      api.get(`/organizations/portal/${encodeURIComponent(slug)}`),
    ),
  updateProfile: (name: string) => data<Me>(api.patch("/users/me", { name })),
  changePassword: (current_password: string, new_password: string) =>
    data(api.put("/users/me/password", { current_password, new_password })),
};

// --- tickets ----------------------------------------------------------------
export interface TicketQuery {
  status?: string;
  priority?: string;
  category?: string;
  team_id?: number;
  assignee?: string;
  requester?: string;
  sla?: "breached" | "at_risk";
  q?: string;
  sort?: string;
  page?: number;
  page_size?: number;
}

export const ticketsApi = {
  list: (params: TicketQuery) => data<Page<Ticket>>(api.get("/tickets", { params })),
  get: (id: number) => data<TicketDetail>(api.get(`/tickets/${id}`)),
  create: (body: { title: string; description: string; priority?: Priority; category?: string }) =>
    data<TicketDetail>(api.post("/tickets", body)),
  update: (id: number, body: Partial<{ title: string; description: string; priority: Priority; category: string; team_id: number | null }>) =>
    data<TicketDetail>(api.patch(`/tickets/${id}`, body)),
  transition: (id: number, body: { to_status: TicketStatus; reason?: string; resolution_summary?: string }) =>
    data<TicketDetail>(api.post(`/tickets/${id}/transitions`, body)),
  assign: (id: number, body: { assignee_id: number | null; team_id?: number | null; reason?: string }) =>
    data<TicketDetail>(api.post(`/tickets/${id}/assign`, body)),
  confirmResolution: (id: number, accepted: boolean, reason?: string) =>
    data<TicketDetail>(api.post(`/tickets/${id}/confirm-resolution`, { accepted, reason })),
  history: (id: number) => data<StatusHistoryEntry[]>(api.get(`/tickets/${id}/history`)),
  comments: (id: number) => data<Comment[]>(api.get(`/tickets/${id}/comments`)),
  addComment: (id: number, content: string, visibility: "public" | "internal") =>
    data<Comment>(api.post(`/tickets/${id}/comments`, { content, visibility })),
  attachments: (id: number) => data<Attachment[]>(api.get(`/tickets/${id}/attachments`)),
  upload: (id: number, file: File, commentId?: number) => {
    const form = new FormData();
    form.append("file", file);
    if (commentId) form.append("comment_id", String(commentId));
    return data<Attachment>(api.post(`/tickets/${id}/attachments`, form));
  },
  download: (attachmentId: number) =>
    api.get<Blob>(`/attachments/${attachmentId}/download`, { responseType: "blob" }).then((r) => r.data),
};

// --- organization -----------------------------------------------------------
export const orgApi = {
  get: () => data<Organization>(api.get("/organizations/me")),
  update: (body: { name?: string; settings?: OrgSettings }) => data<Organization>(api.patch("/organizations/me", body)),
  members: (params: { role?: string; q?: string; include_inactive?: boolean; page?: number; page_size?: number } = {}) =>
    data<Page<UserOut>>(api.get("/organizations/me/members", { params })),
  updateMember: (id: number, body: { role?: Role; is_active?: boolean }) =>
    data<UserOut>(api.patch(`/organizations/me/members/${id}`, body)),
  invitations: () => data<Invitation[]>(api.get("/organizations/me/invitations")),
  invite: (body: { email: string; role: Role; team_id?: number | null }) =>
    data<Invitation & { invite_url: string }>(api.post("/organizations/me/invitations", body)),
  revokeInvitation: (id: number) => data(api.delete(`/organizations/me/invitations/${id}`)),
  teams: () => data<Team[]>(api.get("/teams")),
  createTeam: (body: { name: string; description?: string }) => data<Team>(api.post("/teams", body)),
  updateTeam: (id: number, body: { name: string; description?: string | null }) => data<Team>(api.patch(`/teams/${id}`, body)),
  setTeamMembers: (id: number, user_ids: number[]) => data<Team>(api.put(`/teams/${id}/members`, { user_ids })),
  deleteTeam: (id: number) => data(api.delete(`/teams/${id}`)),
  categories: (includeInactive = false) =>
    data<Category[]>(api.get("/categories", { params: { include_inactive: includeInactive } })),
  createCategory: (body: Omit<Category, "id">) => data<Category>(api.post("/categories", body)),
  updateCategory: (id: number, body: Omit<Category, "id">) => data<Category>(api.put(`/categories/${id}`, body)),
  slaPolicies: () => data<SlaPolicy[]>(api.get("/sla-policies")),
  setSlaPolicies: (policies: SlaPolicy[]) => data<SlaPolicy[]>(api.put("/sla-policies", { policies })),
};

// --- analytics, audit, notifications ----------------------------------------
export const analyticsApi = {
  overview: () => data<Overview>(api.get("/analytics/overview")),
};

export const aiApi = {
  ticket: (id: number) => data<TicketAI>(api.get(`/tickets/${id}/ai`)),
  analyze: (id: number) => data<TicketAI>(api.post(`/tickets/${id}/ai/analyze`)),
  decide: (predictionId: number, decision: "accept" | "edit" | "reject", value?: Record<string, unknown>) =>
    data<AIPrediction>(api.post(`/ai/predictions/${predictionId}/decision`, { decision, value })),
  performance: (days = 30) => data<AIPerformance>(api.get("/analytics/ai-performance", { params: { days } })),
  capabilities: () => data<AICapabilities>(api.get("/ai/capabilities")),
  monitoring: () => data<AIMonitoringRun[]>(api.get("/analytics/ai-monitoring")),
  summary: (id: number) => data<AIPrediction>(api.post(`/tickets/${id}/ai/summary`)),
  replyDraft: (id: number) => data<AIPrediction>(api.post(`/tickets/${id}/ai/reply-draft`)),
  runs: (id: number) => data<AgentRun[]>(api.get(`/tickets/${id}/agent/runs`)),
  queue: (params: { risk?: string; kind?: string; limit?: number } = {}) =>
    data<ApprovalQueue>(api.get("/ai/queue", { params })),
  bulkDecide: (prediction_ids: number[], decision: "accept" | "reject") =>
    data<{ decided: number[]; failed: Record<string, string> }>(api.post("/ai/predictions/bulk-decision", { prediction_ids, decision })),
};

export const kbApi = {
  documents: () => data<KBDocument[]>(api.get("/kb/documents")),
  document: (id: number) => data<KBDocumentDetail>(api.get(`/kb/documents/${id}`)),
  upload: (file: File, visibility: "internal" | "public") => {
    const form = new FormData();
    form.append("file", file);
    form.append("visibility", visibility);
    return data<KBDocument>(api.post("/kb/documents", form));
  },
  update: (id: number, body: { title?: string; visibility?: "internal" | "public" }) =>
    data<KBDocument>(api.patch(`/kb/documents/${id}`, body)),
  reindex: (id: number) => data<KBDocument>(api.post(`/kb/documents/${id}/reindex`)),
  remove: (id: number) => data(api.delete(`/kb/documents/${id}`)),
  search: (q: string, k = 5) => data<KBSearch>(api.get("/kb/search", { params: { q, k } })),
  answer: (question: string) => data<KBAnswer>(api.post("/kb/answer", { question })),
  feedback: (queryId: number, helpful: boolean) => data(api.post(`/kb/queries/${queryId}/feedback`, { helpful })),
  forTicket: (ticketId: number) => data<KBSearch>(api.get(`/tickets/${ticketId}/ai/knowledge`)),
};

export const feedbackApi = {
  csat: (ticketId: number, rating: number, comment?: string) =>
    data(api.post(`/tickets/${ticketId}/csat`, { rating, comment })),
  product: (comment: string, page?: string) => data(api.post("/feedback", { comment, page })),
};

export const auditApi = {
  list: (params: { action?: string; entity_type?: string; entity_id?: string; page?: number; page_size?: number }) =>
    data<Page<AuditEntry>>(api.get("/audit-logs", { params })),
};

export const notificationsApi = {
  list: () => data<NotificationItem[]>(api.get("/notifications")),
  unreadCount: () => data<{ count: number }>(api.get("/notifications/unread-count")),
  markRead: (id: number) => data<NotificationItem>(api.put(`/notifications/${id}/read`)),
  markAllRead: () => data(api.put("/notifications/read-all")),
};
