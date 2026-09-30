import { createTheme } from "@mui/material/styles";

// Neutral enterprise palette: one brand blue, semantic colors reserved for
// status (success/warning/error) so they keep their meaning.
export const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#1f4fd1", dark: "#173c9f", light: "#e8eefc", contrastText: "#ffffff" },
    secondary: { main: "#475569" },
    background: { default: "#f5f6f8", paper: "#ffffff" },
    text: { primary: "#111827", secondary: "#4b5563" },
    divider: "#e5e7eb",
    success: { main: "#15803d" },
    warning: { main: "#b45309" },
    error: { main: "#b91c1c" },
    info: { main: "#0369a1" },
  },
  shape: { borderRadius: 8 },
  typography: {
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    fontSize: 14,
    h1: { fontSize: "1.75rem", fontWeight: 650, letterSpacing: "-0.01em" },
    h2: { fontSize: "1.375rem", fontWeight: 650 },
    h3: { fontSize: "1.125rem", fontWeight: 600 },
    h4: { fontSize: "1rem", fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiPaper: { defaultProps: { elevation: 0 }, styleOverrides: { root: { backgroundImage: "none" } } },
    MuiCard: { styleOverrides: { root: { border: "1px solid #e5e7eb" } } },
    MuiTableCell: { styleOverrides: { head: { fontWeight: 600, color: "#4b5563", backgroundColor: "#fafafa" } } },
    MuiChip: { styleOverrides: { root: { fontWeight: 500 } } },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiSelect: { defaultProps: { size: "small" } },
    MuiAppBar: { defaultProps: { elevation: 0, color: "inherit" } },
  },
});
