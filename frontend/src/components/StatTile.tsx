import ErrorOutlineOutlined from "@mui/icons-material/ErrorOutlineOutlined";
import WarningAmberOutlined from "@mui/icons-material/WarningAmberOutlined";
import { Box, Card, CardContent, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { Link as RouterLink } from "react-router";

import { STATUS_COLOR } from "../lib/chartTheme";

/** One headline number with its label; optionally a link and a status mark (icon + colour). */
export function StatTile({ label, value, hint, to, status }: {
  label: string;
  value: ReactNode;
  hint?: string;
  to?: string;
  status?: "critical" | "warning";
}) {
  const body = (
    <CardContent>
      <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
        {status === "critical" && <ErrorOutlineOutlined sx={{ fontSize: 16, color: STATUS_COLOR.critical }} />}
        {status === "warning" && <WarningAmberOutlined sx={{ fontSize: 16, color: STATUS_COLOR.warning }} />}
        <Typography variant="body2" color="text.secondary">{label}</Typography>
      </Stack>
      <Typography sx={{ fontSize: 28, fontWeight: 650, mt: 0.5, lineHeight: 1.2 }}>{value}</Typography>
      {hint && <Typography variant="caption" color="text.secondary">{hint}</Typography>}
    </CardContent>
  );
  return (
    <Card sx={{ height: "100%" }} role="group" aria-label={label}>
      {to ? (
        <Box component={RouterLink} to={to} sx={{ color: "inherit", textDecoration: "none", display: "block", height: "100%", "&:hover": { bgcolor: "action.hover" } }}>
          {body}
        </Box>
      ) : (
        body
      )}
    </Card>
  );
}
