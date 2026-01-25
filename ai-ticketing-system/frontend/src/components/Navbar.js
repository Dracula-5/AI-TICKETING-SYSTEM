import { AppBar, Toolbar, Button, IconButton, Badge, Box, Tooltip } from "@mui/material";
import NotificationsIcon from "@mui/icons-material/Notifications";
import LogoutIcon from "@mui/icons-material/Logout";
import Brightness4Icon from "@mui/icons-material/Brightness4";
import Brightness7Icon from "@mui/icons-material/Brightness7";
import tenants from "../config/tenantTheme";
import "../styles/navbar.css";

export default function Navbar() {

  const tenantId = localStorage.getItem("tenant_id");
  const theme = tenants[tenantId] || tenants[1];
  const isDark = document.body.classList.contains("dark");

  function logout() {
    localStorage.clear();
    window.location.href = "/";
  }

  function toggleDark() {
    document.body.classList.toggle("dark");
  }

  return (
    <AppBar 
      position="fixed" 
      style={{ 
        background: theme.gradient || theme.color,
        boxShadow: "0 4px 20px rgba(0,0,0,0.1)"
      }}
    >
      <Toolbar sx={{ display: "flex", justifyContent: "space-between", py: 1 }}>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <div className="navbar-logo">
            <span className="navbar-logo-icon">📋</span>
          </div>
          <h3 style={{ 
            margin: 0, 
            fontSize: "18px", 
            fontWeight: 700,
            letterSpacing: "0.5px"
          }}>
            {theme.name}
          </h3>
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {/* Notifications */}
          <Tooltip title="Notifications">
            <IconButton color="inherit" className="navbar-icon-btn">
              <Badge badgeContent={3} color="error">
                <NotificationsIcon />
              </Badge>
            </IconButton>
          </Tooltip>

          {/* Dark Mode Toggle */}
          <Tooltip title={isDark ? "Light Mode" : "Dark Mode"}>
            <IconButton color="inherit" onClick={toggleDark} className="navbar-icon-btn">
              {isDark ? <Brightness7Icon /> : <Brightness4Icon />}
            </IconButton>
          </Tooltip>

          {/* Logout */}
          <Tooltip title="Logout">
            <Button 
              color="inherit" 
              onClick={logout}
              startIcon={<LogoutIcon />}
              className="navbar-logout-btn"
              sx={{
                textTransform: "none",
                fontSize: "14px",
                fontWeight: 600,
                ml: 1
              }}
            >
              Logout
            </Button>
          </Tooltip>
        </Box>

      </Toolbar>
    </AppBar>
  );
}
