import { AppBar, Toolbar, IconButton, Badge, Box, Tooltip } from "@mui/material";
import NotificationsNoneRoundedIcon from "@mui/icons-material/NotificationsNoneRounded";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import SettingsSuggestOutlinedIcon from "@mui/icons-material/SettingsSuggestOutlined";
import LaptopMacOutlinedIcon from "@mui/icons-material/LaptopMacOutlined";
import "../styles/navbar.css";

export default function Navbar() {
  const isDark = document.body.classList.contains("dark");

  function toggleDark() {
    document.body.classList.toggle("dark");
  }

  return (
    <AppBar position="fixed" className="app-navbar" elevation={0}>
      <Toolbar className="app-navbar-toolbar">
        <Box className="navbar-title-wrap">
          <h3>AI Ticketing Dashboard</h3>
          <p>Manage tickets with clarity</p>
        </Box>

        <Box className="navbar-actions">
          <Tooltip title="Preferences">
            <IconButton className="navbar-icon-btn">
              <SettingsSuggestOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>

          <Tooltip title={isDark ? "Light Mode" : "Dark Mode"}>
            <IconButton onClick={toggleDark} className="navbar-icon-btn">
              {isDark ? <LightModeOutlinedIcon fontSize="small" /> : <DarkModeOutlinedIcon fontSize="small" />}
            </IconButton>
          </Tooltip>

          <Tooltip title="Device View">
            <IconButton className="navbar-icon-btn">
              <LaptopMacOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>

          <Tooltip title="Notifications">
            <IconButton className="navbar-icon-btn">
              <Badge badgeContent={4} color="error">
                <NotificationsNoneRoundedIcon fontSize="small" />
              </Badge>
            </IconButton>
          </Tooltip>
        </Box>
      </Toolbar>
    </AppBar>
  );
}
