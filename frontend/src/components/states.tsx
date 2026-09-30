import ErrorOutline from "@mui/icons-material/ErrorOutline";
import InboxOutlined from "@mui/icons-material/InboxOutlined";
import { Alert, Box, Button, CircularProgress, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

import { errorMessage } from "../api/client";

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      spacing={2}
      sx={{ mb: 3, alignItems: { xs: "flex-start", sm: "center" }, justifyContent: "space-between" }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="h1" component="h1">
          {title}
        </Typography>
        {subtitle && (
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {actions && <Stack direction="row" spacing={1}>{actions}</Stack>}
    </Stack>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", py: 6, justifyContent: "center" }} role="status">
      <CircularProgress size={20} />
      <Typography color="text.secondary">{label}</Typography>
    </Stack>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <Stack spacing={1} sx={{ alignItems: "center", textAlign: "center", py: 6, px: 2 }}>
      <InboxOutlined color="disabled" sx={{ fontSize: 40 }} />
      <Typography variant="h4">{title}</Typography>
      {body && <Typography color="text.secondary" sx={{ maxWidth: 420 }}>{body}</Typography>}
      {action && <Box sx={{ pt: 1 }}>{action}</Box>}
    </Stack>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <Alert
      severity="error"
      icon={<ErrorOutline />}
      action={
        onRetry && (
          <Button color="inherit" size="small" onClick={onRetry}>
            Retry
          </Button>
        )
      }
    >
      {errorMessage(error)}
    </Alert>
  );
}
