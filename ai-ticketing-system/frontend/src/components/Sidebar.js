import { Drawer, List, ListItemButton, ListItemIcon, ListItemText, Box, Divider, Avatar, Button } from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import ConfirmationNumberIcon from "@mui/icons-material/ConfirmationNumber";
import AddCircleIcon from "@mui/icons-material/AddCircle";
import AssignmentIndIcon from "@mui/icons-material/AssignmentInd";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import PeopleIcon from "@mui/icons-material/People";
import LogoutIcon from "@mui/icons-material/Logout";
import SettingsIcon from "@mui/icons-material/Settings";
import SchoolIcon from "@mui/icons-material/School";
import { Link, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import "../styles/sidebar.css";

export default function Sidebar({ role }) {
  const location = useLocation();
  const [palette, setPalette] = useState(localStorage.getItem("ui_palette") || "indigo");

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
    ...(role === "admin"
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
          }
        ]
      : [])
  ];

  function logout() {
    localStorage.clear();
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

  const userName = localStorage.getItem("name") || localStorage.getItem("username") || "Signed User";
  const userEmail = localStorage.getItem("email") || "support@company.com";

  return (
    <Drawer
      variant="permanent"
      className="app-sidebar"
      sx={{
        display: { xs: "none", md: "block" },
        "& .MuiDrawer-paper": {
          width: 270,
          boxSizing: "border-box"
        }
      }}
    >
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
    </Drawer>
  );
}
