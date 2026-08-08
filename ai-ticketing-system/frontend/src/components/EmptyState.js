import { Box, Typography, Button } from "@mui/material";
import InboxOutlinedIcon from "@mui/icons-material/InboxOutlined";

/**
 * Shared "nothing here yet" panel for empty lists/tables. Pass `icon` to
 * override the default, `action`/`onAction` for an optional CTA button.
 */
export default function EmptyState({
  icon,
  title = "Nothing here yet",
  description,
  action,
  onAction,
  minHeight = 280,
}) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        gap: 1,
        minHeight,
        width: "100%",
        px: 2,
        color: "text.secondary",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: 56,
          height: 56,
          borderRadius: "50%",
          bgcolor: "action.hover",
          mb: 1,
        }}
      >
        {icon || <InboxOutlinedIcon sx={{ fontSize: 28, color: "text.disabled" }} />}
      </Box>
      <Typography variant="subtitle1" fontWeight={700} color="text.primary">
        {title}
      </Typography>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 380 }}>
          {description}
        </Typography>
      )}
      {action && onAction && (
        <Button variant="contained" size="small" onClick={onAction} sx={{ mt: 1.5, textTransform: "none" }}>
          {action}
        </Button>
      )}
    </Box>
  );
}
