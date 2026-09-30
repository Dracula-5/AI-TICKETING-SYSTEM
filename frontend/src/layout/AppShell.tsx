import AddOutlined from "@mui/icons-material/AddOutlined";
import AdminPanelSettingsOutlined from "@mui/icons-material/AdminPanelSettingsOutlined";
import CategoryOutlined from "@mui/icons-material/CategoryOutlined";
import ConfirmationNumberOutlined from "@mui/icons-material/ConfirmationNumberOutlined";
import DashboardOutlined from "@mui/icons-material/DashboardOutlined";
import GroupsOutlined from "@mui/icons-material/GroupsOutlined";
import HistoryEduOutlined from "@mui/icons-material/HistoryEduOutlined";
import InboxOutlined from "@mui/icons-material/InboxOutlined";
import MenuOutlined from "@mui/icons-material/MenuOutlined";
import PeopleOutline from "@mui/icons-material/PeopleOutline";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import TimerOutlined from "@mui/icons-material/TimerOutlined";
import {
  Alert,
  AppBar,
  Avatar,
  Box,
  Button,
  Chip,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  Menu,
  MenuItem,
  Toolbar,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { errorMessage } from "../api/client";
import { authApi } from "../api/endpoints";
import { useAuth } from "../auth/AuthProvider";
import { Brand } from "../components/Brand";
import { NotificationBell } from "../components/NotificationBell";
import { useToast } from "../components/Toast";
import { useNotificationSocket } from "../hooks/useNotificationSocket";
import { ROLE } from "../lib/labels";

const DRAWER_WIDTH = 248;

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  permission?: string;
  end?: boolean;
}

const WORK: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: <DashboardOutlined />, permission: "analytics:read" },
  { to: "/tickets?view=mine", label: "My work", icon: <InboxOutlined />, permission: "tickets:work" },
  { to: "/tickets?view=queue", label: "Team queue", icon: <GroupsOutlined />, permission: "tickets:work" },
  { to: "/tickets", label: "All tickets", icon: <ConfirmationNumberOutlined />, permission: "tickets:read_all", end: true },
  { to: "/tickets?view=sla", label: "SLA monitor", icon: <TimerOutlined />, permission: "tickets:read_all" },
];

const ADMIN: NavItem[] = [
  { to: "/admin/members", label: "Users & invitations", icon: <PeopleOutline />, permission: "users:invite" },
  { to: "/admin/teams", label: "Teams", icon: <GroupsOutlined />, permission: "teams:manage" },
  { to: "/admin/categories", label: "Categories & routing", icon: <CategoryOutlined />, permission: "categories:manage" },
  { to: "/admin/sla", label: "SLA policies", icon: <TimerOutlined />, permission: "sla:manage" },
  { to: "/admin/settings", label: "Organization", icon: <AdminPanelSettingsOutlined />, permission: "org:update" },
  { to: "/audit", label: "Audit log", icon: <HistoryEduOutlined />, permission: "audit:read" },
];

function NavSection({ title, items, onNavigate }: { title?: string; items: NavItem[]; onNavigate: () => void }) {
  const { can } = useAuth();
  const location = useLocation();
  const visible = items.filter((i) => !i.permission || can(i.permission));
  if (visible.length === 0) return null;
  const current = location.pathname + location.search;
  return (
    <List dense subheader={title ? <ListSubheader sx={{ bgcolor: "transparent" }}>{title}</ListSubheader> : undefined}>
      {visible.map((item) => {
        const selected = item.to.includes("?") ? current === item.to : location.pathname === item.to && !location.search;
        return (
          <ListItemButton key={item.to} component={NavLink} to={item.to} selected={selected} onClick={onNavigate} sx={{ borderRadius: 1, mx: 1 }}>
            <ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon>
            <ListItemText primary={item.label} />
          </ListItemButton>
        );
      })}
    </List>
  );
}

export function AppShell() {
  const { me, can, logout } = useAuth();
  const theme = useTheme();
  const desktop = useMediaQuery(theme.breakpoints.up("md"));
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const navigate = useNavigate();
  const toast = useToast();

  useNotificationSocket(!!me, (n) => toast(n.title, "info"));

  if (!me) return null;
  const isRequester = !can("tickets:read_all");

  const drawer = (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Toolbar sx={{ px: 2 }}>
        <Brand />
      </Toolbar>
      <Divider />
      <Box sx={{ p: 1.5 }}>
        {can("tickets:create") && (
          <Button fullWidth variant="contained" startIcon={<AddOutlined />} component={NavLink} to="/tickets/new" onClick={() => setMobileOpen(false)}>
            New ticket
          </Button>
        )}
      </Box>
      {isRequester ? (
        <NavSection items={[{ to: "/tickets", label: "My tickets", icon: <ConfirmationNumberOutlined />, end: true }]} onNavigate={() => setMobileOpen(false)} />
      ) : (
        <NavSection items={WORK} onNavigate={() => setMobileOpen(false)} />
      )}
      <NavSection title="Administration" items={ADMIN} onNavigate={() => setMobileOpen(false)} />
      <Box sx={{ flexGrow: 1 }} />
      <Divider />
      <Box sx={{ p: 2 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          {me.organization?.name}
        </Typography>
        {me.organization?.is_demo && <Chip size="small" label="Demo organization" color="warning" variant="outlined" sx={{ mt: 0.5 }} />}
      </Box>
    </Box>
  );

  const resend = async () => {
    try {
      await authApi.resendVerification();
      toast("Verification email sent");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <AppBar position="fixed" sx={{ borderBottom: 1, borderColor: "divider", width: { md: `calc(100% - ${DRAWER_WIDTH}px)` }, ml: { md: `${DRAWER_WIDTH}px` } }}>
        <Toolbar sx={{ gap: 1 }}>
          {!desktop && (
            <IconButton edge="start" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
              <MenuOutlined />
            </IconButton>
          )}
          <Box sx={{ flexGrow: 1 }} />
          <NotificationBell />
          <Button onClick={(e) => setMenuAnchor(e.currentTarget)} sx={{ color: "text.primary", gap: 1 }} aria-label="Account menu">
            <Avatar sx={{ width: 30, height: 30, fontSize: 14, bgcolor: "primary.main" }}>{me.name.slice(0, 1).toUpperCase()}</Avatar>
            <Box sx={{ display: { xs: "none", sm: "block" }, textAlign: "left", lineHeight: 1.2 }}>
              <Typography variant="body2" component="span" sx={{ fontWeight: 600, display: "block" }}>{me.name}</Typography>
              <Typography variant="caption" component="span" color="text.secondary" sx={{ display: "block" }}>{ROLE[me.role]}</Typography>
            </Box>
          </Button>
          <Menu anchorEl={menuAnchor} open={!!menuAnchor} onClose={() => setMenuAnchor(null)}>
            <MenuItem onClick={() => { setMenuAnchor(null); navigate("/profile"); }}>
              <ListItemIcon><SettingsOutlined fontSize="small" /></ListItemIcon>
              Profile & security
            </MenuItem>
            <MenuItem onClick={async () => { setMenuAnchor(null); await logout(); navigate("/login"); }}>Sign out</MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}>
        <Drawer
          variant={desktop ? "permanent" : "temporary"}
          open={desktop || mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{ "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box", borderRight: 1, borderColor: "divider" } }}
        >
          {drawer}
        </Drawer>
      </Box>

      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, width: { md: `calc(100% - ${DRAWER_WIDTH}px)` } }}>
        <Toolbar />
        {me.organization?.is_demo && (
          <Alert severity="warning" square sx={{ borderBottom: 1, borderColor: "divider" }}>
            You are in a shared demo organization. Its data is illustrative, not real usage, and some settings are locked.
          </Alert>
        )}
        {!me.email_verified_at && !me.organization?.is_demo && (
          <Alert severity="info" square action={<Button color="inherit" size="small" onClick={resend}>Resend email</Button>}>
            Please verify your email address — check your inbox for the link.
          </Alert>
        )}
        <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1400, mx: "auto" }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
