import { Drawer, List, ListItemButton, ListItemIcon, ListItemText, Box, Divider, Avatar, Button } from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import ConfirmationNumberIcon from "@mui/icons-material/ConfirmationNumber";
import AddCircleIcon from "@mui/icons-material/AddCircle";
import AssignmentIndIcon from "@mui/icons-material/AssignmentInd";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import PeopleIcon from "@mui/icons-material/People";
import StorefrontIcon from "@mui/icons-material/Storefront";
import StoreIcon from "@mui/icons-material/Store";
import ReceiptLongIcon from "@mui/icons-material/ReceiptLong";
import ChatIcon from "@mui/icons-material/Chat";
import VerifiedIcon from "@mui/icons-material/Verified";
import FactCheckIcon from "@mui/icons-material/FactCheck";
import InsightsIcon from "@mui/icons-material/Insights";
import LogoutIcon from "@mui/icons-material/Logout";
import SettingsIcon from "@mui/icons-material/Settings";
import SchoolIcon from "@mui/icons-material/School";
import TuneIcon from "@mui/icons-material/Tune";
import { Link, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { clearAuthSession, getAuthItem } from "../utils/authSession";
import { useUI } from "../context/UIContext";
import "../styles/sidebar.css";

const DRAWER_WIDTH = 270;

export default function Sidebar({ role }) {
  const location = useLocation();
  const effectiveRole = getAuthItem("role") || role;
  const [palette, setPalette] = useState(localStorage.getItem("ui_palette") || "indigo");
  const { mobileNavOpen, setMobileNavOpen } = useUI();

  const menuItems = [
    {
      label: "Dashboard",
      icon: <DashboardIcon />,
      path: "/dashboard"
    },
    {
      label: "All Tickets",
      icon: <ConfirmationNumberIcon />,
      path: "/tickets"
    },
    {
      label: "Create Ticket",
      icon: <AddCircleIcon />,
      path: "/create-ticket"
    },
    {
      label: "AI Create",
      icon: <SmartToyIcon />,
      path: "/ai-ticket"
    },
    {
      label: "Marketplace",
      icon: <StorefrontIcon />,
      path: "/marketplace"
    },
    ...(effectiveRole === "customer"
      ? [
          {
            label: "My Orders",
            icon: <ReceiptLongIcon />,
            path: "/orders"
          }
        ]
      : []),
    ...(effectiveRole === "vendor"
      ? [
          {
            label: "Vendor Dashboard",
            icon: <StoreIcon />,
            path: "/vendor/dashboard"
          },
          {
            label: "Negotiation Inbox",
            icon: <ChatIcon />,
            path: "/vendor/inbox"
          }
        ]
      : []),
    ...(effectiveRole === "provider" || effectiveRole === "service_provider"
      ? [
          {
            label: "My Categories",
            icon: <TuneIcon />,
            path: "/provider/preferences"
          }
        ]
      : []),
    ...(effectiveRole === "admin"
      ? [
          {
            label: "Assign Tickets",
            icon: <AssignmentIndIcon />,
            path: "/assign"
          },
          {
            label: "Users",
            icon: <PeopleIcon />,
            path: "/users"
          },
          {
            label: "Vendor Verification",
            icon: <VerifiedIcon />,
            path: "/admin/vendors"
          },
          {
            label: "Product Moderation",
            icon: <FactCheckIcon />,
            path: "/admin/products"
          },
          {
            label: "Analytics",
            icon: <InsightsIcon />,
            path: "/admin/analytics"
          }
        ]
      : [])
  ];

  function logout() {
    clearAuthSession();
    window.location.href = "/";
  }

  function changePalette(nextPalette) {
    setPalette(nextPalette);
    localStorage.setItem("ui_palette", nextPalette);
    document.body.setAttribute("data-palette", nextPalette);
  }

  useEffect(() => {
    document.body.setAttribute("data-palette", palette);
  }, [palette]);

  const userName = getAuthItem("name") || getAuthItem("username") || "Signed User";
  const userEmail = getAuthItem("email") || "support@company.com";

  const sidebarContent = (
    <Box className="sidebar-shell">
      <Box className="sidebar-brand">
        <Avatar className="sidebar-brand-avatar">
          <SchoolIcon fontSize="small" />
        </Avatar>
        <Box>
          <h2>Smart Ticketing System</h2>
          <p>Workspace</p>
        </Box>
      </Box>

      <Box className="sidebar-palette">
        <span className="palette-title">Palette</span>
        <div className="palette-row">
          <button
            className={`palette-chip palette-indigo${palette === "indigo" ? " active" : ""}`}
            aria-label="Indigo palette"
            type="button"
            onClick={() => changePalette("indigo")}
          >
            <i />
            <i />
            <i />
          </button>
          <button
            className={`palette-chip palette-ocean${palette === "ocean" ? " active" : ""}`}
            aria-label="Ocean palette"
            type="button"
            onClick={() => changePalette("ocean")}
          >
            <i />
            <i />
            <i />
          </button>
          <button
            className={`palette-chip palette-sunset${palette === "sunset" ? " active" : ""}`}
            aria-label="Sunset palette"
            type="button"
            onClick={() => changePalette("sunset")}
          >
            <i />
            <i />
            <i />
          </button>
        </div>
      </Box>

      <Divider className="sidebar-divider" />

      <List className="sidebar-menu-list">
        {menuItems.map((item) => {
          const active = location.pathname === item.path;
          return (
            <ListItemButton
              key={item.path}
              component={Link}
              to={item.path}
              onClick={() => setMobileNavOpen(false)}
              className={`sidebar-menu-item${active ? " active" : ""}`}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          );
        })}

        <ListItemButton className="sidebar-menu-item sidebar-muted-item">
          <ListItemIcon>
            <SettingsIcon />
          </ListItemIcon>
          <ListItemText primary="Settings" />
        </ListItemButton>
      </List>

      <Box className="sidebar-footer">
        <Box className="sidebar-user">
          <Avatar className="sidebar-user-avatar">{userName.charAt(0).toUpperCase()}</Avatar>
          <Box>
            <h4>{userName}</h4>
            <p>{userEmail}</p>
          </Box>
        </Box>

        <Button
          fullWidth
          variant="outlined"
          onClick={logout}
          startIcon={<LogoutIcon />}
          className="sidebar-logout"
        >
          Sign Out
        </Button>
      </Box>
    </Box>
  );

  return (
    <>
      {/* Desktop: permanent drawer, always visible at md+ */}
      <Drawer
        variant="permanent"
        className="app-sidebar"
        sx={{
          display: { xs: "none", md: "block" },
          "& .MuiDrawer-paper": {
            width: DRAWER_WIDTH,
            boxSizing: "border-box"
          }
        }}
      >
        {sidebarContent}
      </Drawer>

      {/* Mobile: temporary overlay drawer, opened via the Navbar hamburger button */}
      <Drawer
        variant="temporary"
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: "block", md: "none" },
          "& .MuiDrawer-paper": {
            width: DRAWER_WIDTH,
            boxSizing: "border-box"
          }
        }}
      >
        {sidebarContent}
      </Drawer>
    </>
  );
}
