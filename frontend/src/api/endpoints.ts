import { api } from "./client";
import type {
  AuditEntry,
  Attachment,
  Category,
  Comment,
  Invitation,
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
