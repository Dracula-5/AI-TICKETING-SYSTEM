import NotificationsOutlined from "@mui/icons-material/NotificationsOutlined";
import {
  Badge,
  Box,
  Button,
  Divider,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Popover,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";

import { notificationsApi } from "../api/endpoints";
import type { NotificationItem } from "../api/types";
import { formatRelative } from "../lib/format";

export function NotificationBell() {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const count = useQuery({ queryKey: ["notifications", "count"], queryFn: notificationsApi.unreadCount, refetchInterval: 60_000 });
  const list = useQuery({ queryKey: ["notifications", "list"], queryFn: notificationsApi.list, enabled: !!anchor });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notifications"] });
  const markRead = useMutation({ mutationFn: notificationsApi.markRead, onSuccess: invalidate });
  const markAll = useMutation({ mutationFn: notificationsApi.markAllRead, onSuccess: invalidate });

  const open = (n: NotificationItem) => {
    if (!n.is_read) markRead.mutate(n.id);
    setAnchor(null);
    if (n.link) navigate(n.link);
  };

  const unread = count.data?.count ?? 0;
  return (
    <>
      <Tooltip title="Notifications">
        <IconButton onClick={(e) => setAnchor(e.currentTarget)} aria-label={`Notifications, ${unread} unread`}>
          <Badge badgeContent={unread} color="error" max={99}>
            <NotificationsOutlined />
          </Badge>
        </IconButton>
      </Tooltip>
      <Popover
        open={!!anchor}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { width: 380, maxWidth: "calc(100vw - 32px)", border: 1, borderColor: "divider" } } }}
      >
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 2, py: 1.5 }}>
          <Typography variant="h4">Notifications</Typography>
          <Button size="small" disabled={!unread} onClick={() => markAll.mutate()}>
            Mark all read
          </Button>
        </Box>
        <Divider />
        {list.isLoading && <Typography sx={{ p: 2 }} color="text.secondary">Loading…</Typography>}
        {list.data?.length === 0 && (
          <Typography sx={{ p: 2 }} color="text.secondary">
            You're all caught up.
          </Typography>
        )}
        <List dense disablePadding sx={{ maxHeight: 420, overflow: "auto" }}>
          {list.data?.map((n) => (
            <ListItemButton key={n.id} onClick={() => open(n)} sx={{ alignItems: "flex-start", bgcolor: n.is_read ? undefined : "primary.light" }}>
              <ListItemText
                primary={n.title}
                secondary={
                  <>
                    {n.message && <Box component="span" sx={{ display: "block" }}>{n.message}</Box>}
                    <Box component="span" sx={{ color: "text.disabled" }}>{formatRelative(n.created_at)}</Box>
                  </>
                }
                slotProps={{ primary: { sx: { fontWeight: n.is_read ? 400 : 600 } } }}
              />
            </ListItemButton>
          ))}
        </List>
      </Popover>
    </>
  );
}
