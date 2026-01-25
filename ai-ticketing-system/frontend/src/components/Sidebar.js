import { Drawer, List, ListItemButton, ListItemIcon, ListItemText, Box, Divider } from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import ConfirmationNumberIcon from "@mui/icons-material/ConfirmationNumber";
import AddCircleIcon from "@mui/icons-material/AddCircle";
import AssignmentIndIcon from "@mui/icons-material/AssignmentInd";
import { Link } from "react-router-dom";
import tenants from "../config/tenantTheme";
import "../styles/sidebar.css";

export default function Sidebar({ role }) {

  const isMobile = window.innerWidth < 768;

  const tenantId = localStorage.getItem("tenant_id");
  const theme = tenants[tenantId] || tenants[1];

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
    ...(role === "admin" ? [{
      label: "Assign Tickets",
      icon: <AssignmentIndIcon />,
      path: "/assign"
    }] : [])
  ];

  return (
    <Drawer
      variant={isMobile ? "temporary" : "permanent"}
      anchor="left"
      open={true}
      sx={{
        "& .MuiDrawer-paper": {
          width: 270,
          background: `linear-gradient(180deg, ${theme.color} 0%, ${theme.darkColor} 100%)`,
          color: "white",
          boxShadow: "4px 0 16px rgba(0,0,0,0.1)",
          borderRight: "1px solid rgba(255,255,255,0.1)"
        }
      }}
    >
      <List sx={{ height: "100%", display: "flex", flexDirection: "column", pt: 2 }}>

        {/* Logo Section */}
        <Box sx={{ px: 2, pb: 2, mb: 1 }}>
          <Box className="sidebar-logo-section">
            <span className="sidebar-logo-icon">📋</span>
            <h2 style={{ margin: "0 0 4px 0", fontSize: "18px", fontWeight: 700 }}>
              {theme.name.split(" ")[0]}
            </h2>
            <p style={{ margin: 0, fontSize: "11px", opacity: 0.8 }}>Ticketing System</p>
          </Box>
        </Box>

        <Divider sx={{ borderColor: "rgba(255,255,255,0.1)", my: 1 }} />

        {/* Menu Items */}
        {menuItems.map((item) => (
          <ListItemButton
            key={item.path}
            component={Link}
            to={item.path}
            className="sidebar-menu-item"
          >
            <ListItemIcon sx={{ color: "white", minWidth: 40 }}>
              {item.icon}
            </ListItemIcon>
            <ListItemText 
              primary={item.label}
              sx={{
                "& .MuiListItemText-primary": {
                  fontSize: "14px",
                  fontWeight: 500,
                  letterSpacing: "0.3px"
                }
              }}
            />
          </ListItemButton>
        ))}

        {/* Spacer */}
        <Box sx={{ flexGrow: 1 }} />

        {/* Footer */}
        <Divider sx={{ borderColor: "rgba(255,255,255,0.1)", my: 1 }} />
        <Box sx={{ p: 2, textAlign: "center", fontSize: "12px", opacity: 0.7 }}>
          <p style={{ margin: 0 }}>v1.0.0</p>
        </Box>

      </List>
    </Drawer>
  );
}
