import { Box, Paper, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

import { Brand } from "../../components/Brand";

export function AuthCard({ title, subtitle, children, footer }: { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", p: 2, bgcolor: "background.default" }}>
      <Stack spacing={3} sx={{ width: "100%", maxWidth: 420, alignItems: "center" }}>
        <Brand />
        <Paper sx={{ p: { xs: 3, sm: 4 }, width: "100%", border: 1, borderColor: "divider" }}>
          <Typography variant="h2" component="h1" sx={{ mb: subtitle ? 0.5 : 3 }}>
            {title}
          </Typography>
          {subtitle && (
            <Typography color="text.secondary" sx={{ mb: 3 }}>
              {subtitle}
            </Typography>
          )}
          {children}
        </Paper>
        {footer && <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>{footer}</Typography>}
      </Stack>
    </Box>
  );
}
