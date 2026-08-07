import { createTheme } from "@mui/material/styles";

// Mirrors the custom-property palette in src/index.css (--accent / --accent-strong
// for the default "indigo" data-palette) so MUI's own colored elements (buttons,
// chips, progress bars) stop clashing with MUI's default blue and read as part of
// the same design system as the hand-styled pages.
const theme = createTheme({
  palette: {
    primary: {
      main: "#4f46e5",
      dark: "#4338ca",
    },
    secondary: {
      main: "#0f766e",
    },
  },
  typography: {
    fontFamily: '"Plus Jakarta Sans", "Poppins", "Segoe UI", sans-serif',
    button: {
      textTransform: "none",
      fontWeight: 600,
    },
  },
  shape: {
    borderRadius: 10,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 600,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 14,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 14,
        },
      },
    },
    MuiTextField: {
      defaultProps: {
        size: "medium",
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: 10,
        },
      },
    },
  },
});

export default theme;
