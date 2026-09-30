import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";

import { useAuth } from "./auth/AuthProvider";
import { homePath } from "./auth/homePath";
import { Loading } from "./components/states";
import { AppShell } from "./layout/AppShell";
import { AuditLogPage, NotFoundPage, PlatformPage, ProfilePage } from "./pages/OtherPages";
import { LandingPage } from "./pages/public/LandingPage";
import { LoginPage } from "./pages/public/LoginPage";
import { RegisterPage } from "./pages/public/RegisterPage";
import { AcceptInvitePage, ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage } from "./pages/public/TokenPages";
import { NewTicketPage } from "./pages/tickets/NewTicketPage";
import { TicketDetailPage } from "./pages/tickets/TicketDetailPage";
import { TicketListPage } from "./pages/tickets/TicketListPage";

// Route-level code splitting: charts and admin screens load only when opened.
const ApprovalQueuePage = lazy(() => import("./pages/ApprovalQueuePage").then((m) => ({ default: m.ApprovalQueuePage })));
const AINoticePage = lazy(() => import("./pages/public/AINoticePage").then((m) => ({ default: m.AINoticePage })));
const KnowledgePage = lazy(() => import("./pages/kb/KnowledgePage").then((m) => ({ default: m.KnowledgePage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const MembersPage = lazy(() => import("./pages/admin/MembersPage").then((m) => ({ default: m.MembersPage })));
const config = () => import("./pages/admin/ConfigPages");
const TeamsPage = lazy(() => config().then((m) => ({ default: m.TeamsPage })));
const CategoriesPage = lazy(() => config().then((m) => ({ default: m.CategoriesPage })));
const SlaPoliciesPage = lazy(() => config().then((m) => ({ default: m.SlaPoliciesPage })));
const OrgSettingsPage = lazy(() => config().then((m) => ({ default: m.OrgSettingsPage })));

function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <Loading label="Restoring your session…" />;
  if (status === "anonymous") return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

/** Client-side gate for navigation only — the API enforces every permission. */
function RequirePermission({ permission, children }: { permission: string; children: ReactNode }) {
  const { can } = useAuth();
  return can(permission) ? <Suspense fallback={<Loading />}>{children}</Suspense> : <NotFoundPage />;
}

/** Public auth pages. Once a session exists this guard performs the one
 * redirect — to the destination the sign-in requested, else the home page. */
function PublicOnly({ children }: { children: ReactNode }) {
  const { status, me, nextPath } = useAuth();
  if (status === "loading") return <Loading />;
  if (status === "authenticated" && me) return <Navigate to={nextPath ?? homePath(me)} replace />;
  return <>{children}</>;
}

function Home() {
  const { me } = useAuth();
  return me ? <Navigate to={homePath(me)} replace /> : null;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/ai-notice" element={<AINoticePage />} />
      <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><RegisterPage /></PublicOnly>} />
      <Route path="/join/:slug" element={<PublicOnly><RegisterPage /></PublicOnly>} />
      <Route path="/accept-invite" element={<AcceptInvitePage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route element={<RequireAuth><AppShell /></RequireAuth>}>
        <Route path="/home" element={<Home />} />
        <Route path="/dashboard" element={<RequirePermission permission="analytics:read"><DashboardPage /></RequirePermission>} />
        <Route path="/tickets" element={<TicketListPage />} />
        <Route path="/tickets/new" element={<RequirePermission permission="tickets:create"><NewTicketPage /></RequirePermission>} />
        <Route path="/tickets/:id" element={<TicketDetailPage />} />
        <Route path="/admin/members" element={<RequirePermission permission="users:invite"><MembersPage /></RequirePermission>} />
        <Route path="/admin/teams" element={<RequirePermission permission="teams:manage"><TeamsPage /></RequirePermission>} />
        <Route path="/admin/categories" element={<RequirePermission permission="categories:manage"><CategoriesPage /></RequirePermission>} />
        <Route path="/admin/sla" element={<RequirePermission permission="sla:manage"><SlaPoliciesPage /></RequirePermission>} />
        <Route path="/admin/settings" element={<RequirePermission permission="org:update"><OrgSettingsPage /></RequirePermission>} />
        <Route path="/audit" element={<RequirePermission permission="audit:read"><AuditLogPage /></RequirePermission>} />
        <Route path="/platform" element={<RequirePermission permission="platform:admin"><PlatformPage /></RequirePermission>} />
        <Route path="/ai/approvals" element={<RequirePermission permission="tickets:work"><ApprovalQueuePage /></RequirePermission>} />
        <Route path="/kb" element={<RequirePermission permission="kb:read"><KnowledgePage /></RequirePermission>} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
