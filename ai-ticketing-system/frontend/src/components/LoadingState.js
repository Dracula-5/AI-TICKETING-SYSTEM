import { Box, CircularProgress, Typography } from "@mui/material";

/**
 * Drop-in replacement for "render nothing while data loads". Sized for a
 * page's main content area, not a full-screen overlay -- Navbar/Sidebar stay
 * visible and interactive while this shows.
 */
export default function LoadingState({ label = "Loading...", minHeight = 320 }) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 2,
        minHeight,
        width: "100%",
        color: "text.secondary",
      }}
    >
      <CircularProgress size={36} thickness={4} sx={{ color: "var(--accent)" }} />
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
    </Box>
  );
}
