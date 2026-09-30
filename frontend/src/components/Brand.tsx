import { Box, Typography } from "@mui/material";
import { Link } from "react-router";

export function Brand({ to = "/" }: { to?: string }) {
  return (
    <Box component={Link} to={to} sx={{ display: "flex", alignItems: "center", gap: 1, color: "inherit", textDecoration: "none" }}>
      <Box component="img" src="/favicon.svg" alt="" sx={{ width: 28, height: 28 }} />
      <Typography sx={{ fontWeight: 700, fontSize: 17, letterSpacing: "-0.01em" }}>
        NexaDesk <Box component="span" sx={{ color: "primary.main" }}>AI</Box>
      </Typography>
    </Box>
  );
}
