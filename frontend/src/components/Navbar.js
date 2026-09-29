import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  AppBar, Toolbar, IconButton, Badge, Box, Tooltip, Menu, MenuItem, Typography, Divider, Button, Chip,
} from "@mui/material";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import NotificationsNoneRoundedIcon from "@mui/icons-material/NotificationsNoneRounded";
import DarkModeOutlinedIcon from "@mui/icons-material/DarkModeOutlined";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import SettingsSuggestOutlinedIcon from "@mui/icons-material/SettingsSuggestOutlined";
import LaptopMacOutlinedIcon from "@mui/icons-material/LaptopMacOutlined";
import StorefrontIcon from "@mui/icons-material/Storefront";
import ShoppingCartOutlinedIcon from "@mui/icons-material/ShoppingCartOutlined";
import { useUI } from "../context/UIContext";
import { useNotifications } from "../context/NotificationContext";
import { useCart } from "../context/CartContext";
import "../styles/navbar.css";

const MARKETPLACE_PATH_PREFIXES = [
  "/marketplace", "/product/", "/vendor/dashboard", "/vendor/inbox",
  "/negotiation/", "/orders", "/cart", "/checkout",
];

function timeAgo(isoString) {
  const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function Navbar() {
  const isDark = document.body.classList.contains("dark");
  const { setMobileNavOpen } = useUI();
  const { notifications, unreadCount, markRead, markAllRead } = useNotifications();
  const { totalCount } = useCart();
  const [anchorEl, setAnchorEl] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  const inMarketplace = MARKETPLACE_PATH_PREFIXES.some((p) => location.pathname.startsWith(p));

  function toggleDark() {
    document.body.classList.toggle("dark");
  }

  function handleNotificationClick(entry) {
    setAnchorEl(null);
    if (!entry.is_read) markRead(entry.id);
    if (entry.link) navigate(entry.link);
  }

  return (
    <AppBar position="fixed" className={`app-navbar${inMarketplace ? " navbar-marketplace" : ""}`} elevation={0}>
      <Toolbar className="app-navbar-toolbar">
        <IconButton
          className="navbar-icon-btn navbar-menu-btn"
          sx={{ display: { xs: "inline-flex", md: "none" }, mr: 1 }}
          onClick={() => setMobileNavOpen(true)}
          aria-label="Open navigation menu"
        >
          <MenuRoundedIcon fontSize="small" />
        </IconButton>

        <Box className="navbar-title-wrap" sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Box>
            {inMarketplace ? (
              <>
                <h3>Marketplace</h3>
                <p>Shop, negotiate, and track orders</p>
              </>
            ) : (
              <>
                <h3>AI Ticketing Dashboard</h3>
                <p>Manage tickets with clarity</p>
              </>
            )}
          </Box>
          {inMarketplace && (
            <Chip icon={<StorefrontIcon />} label="Marketplace" size="small" variant="outlined" sx={{ display: { xs: "none", sm: "flex" } }} />
          )}
        </Box>

        <Box className="navbar-actions">
          {inMarketplace && (
            <Tooltip title="Cart">
              <IconButton className="navbar-icon-btn" onClick={() => navigate("/cart")} aria-label="Cart">
                <Badge badgeContent={totalCount} color="error">
                  <ShoppingCartOutlinedIcon fontSize="small" />
                </Badge>
              </IconButton>
            </Tooltip>
          )}

          <Tooltip title="Preferences">
            <IconButton className="navbar-icon-btn" onClick={() => navigate("/settings")} aria-label="Preferences">
              <SettingsSuggestOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>

          <Tooltip title={isDark ? "Light Mode" : "Dark Mode"}>
            <IconButton onClick={toggleDark} className="navbar-icon-btn" aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}>
              {isDark ? <LightModeOutlinedIcon fontSize="small" /> : <DarkModeOutlinedIcon fontSize="small" />}
            </IconButton>
          </Tooltip>

          <Tooltip title="Device View">
            <IconButton className="navbar-icon-btn" aria-label="Device view">
              <LaptopMacOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>

          <Tooltip title="Notifications">
            <IconButton
              className="navbar-icon-btn"
              onClick={(e) => setAnchorEl(e.currentTarget)}
              aria-label="Notifications"
            >
              <Badge badgeContent={unreadCount} color="error">
                <NotificationsNoneRoundedIcon fontSize="small" />
              </Badge>
            </IconButton>
          </Tooltip>

          <Menu
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={() => setAnchorEl(null)}
            slotProps={{ paper: { sx: { width: 360, maxHeight: 420 } } }}
          >
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, py: 1 }}>
              <Typography variant="subtitle2" fontWeight={700}>Notifications</Typography>
              {unreadCount > 0 && (
                <Button size="small" onClick={markAllRead}>Mark all read</Button>
              )}
            </Box>
            <Divider />
            {notifications.length === 0 ? (
              <MenuItem disabled>No notifications yet</MenuItem>
            ) : (
              notifications.slice(0, 15).map((entry) => (
                <MenuItem
                  key={entry.id}
                  onClick={() => handleNotificationClick(entry)}
                  sx={{
                    whiteSpace: "normal",
                    alignItems: "flex-start",
                    py: 1,
                    backgroundColor: entry.is_read ? "transparent" : "action.hover",
                  }}
                >
                  <Box sx={{ width: "100%" }}>
                    <Typography variant="body2" fontWeight={entry.is_read ? 400 : 700}>
                      {entry.title}
                    </Typography>
                    {entry.message && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                        {entry.message}
                      </Typography>
                    )}
                    <Typography variant="caption" color="text.disabled">
                      {timeAgo(entry.created_at)}
                    </Typography>
                  </Box>
                </MenuItem>
              ))
            )}
          </Menu>
        </Box>
      </Toolbar>
    </AppBar>
  );
}
