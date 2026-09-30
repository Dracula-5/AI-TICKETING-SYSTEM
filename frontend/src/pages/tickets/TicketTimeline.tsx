import AttachFileOutlined from "@mui/icons-material/AttachFileOutlined";
import LockOutlined from "@mui/icons-material/LockOutlined";
import RuleOutlined from "@mui/icons-material/RuleOutlined";
import SyncAltOutlined from "@mui/icons-material/SyncAltOutlined";
import { Avatar, Box, Chip, Link, Paper, Stack, Typography } from "@mui/material";

import type { Attachment, Comment, StatusHistoryEntry } from "../../api/types";
import { formatBytes, formatDateTime, formatRelative } from "../../lib/format";
import { ROLE, STATUS } from "../../lib/labels";

type Item =
  | { kind: "comment"; at: string; comment: Comment }
  | { kind: "status"; at: string; entry: StatusHistoryEntry };

export function buildTimeline(comments: Comment[], history: StatusHistoryEntry[]): Item[] {
  const items: Item[] = [
    ...comments.map((c) => ({ kind: "comment" as const, at: c.created_at, comment: c })),
    ...history.map((h) => ({ kind: "status" as const, at: h.created_at, entry: h })),
  ];
  return items.sort((a, b) => a.at.localeCompare(b.at));
}

function StatusEvent({ entry }: { entry: StatusHistoryEntry }) {
  const who =
    entry.actor_type === "system" ? "System" : entry.actor_type === "ai" ? "AI" : entry.actor?.name ?? "Someone";
  const verb = entry.from_status === null ? "created the ticket" : `moved it to ${STATUS[entry.to_status].label}`;
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-start", py: 0.5 }}>
      <Box sx={{ width: 32, display: "flex", justifyContent: "center", pt: 0.25, color: "text.secondary" }}>
        {entry.actor_type === "system" ? <RuleOutlined fontSize="small" /> : <SyncAltOutlined fontSize="small" />}
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2" component="div">
          <strong>{who}</strong> {verb}
          {entry.actor_type === "system" && <Chip size="small" label="System rule" variant="outlined" sx={{ ml: 1, borderStyle: "dashed", height: 20 }} />}
          <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }} title={formatDateTime(entry.created_at)}>
            {formatRelative(entry.created_at)}
          </Typography>
        </Typography>
        {entry.reason && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, overflowWrap: "anywhere" }}>
            {entry.reason}
          </Typography>
        )}
      </Box>
    </Stack>
  );
}

function CommentBubble({ comment, onDownload }: { comment: Comment; onDownload: (a: Attachment) => void }) {
  const internal = comment.visibility === "internal";
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-start" }}>
      <Avatar sx={{ width: 32, height: 32, fontSize: 14, bgcolor: internal ? "warning.main" : "primary.main" }}>
        {(comment.author?.name ?? "?").slice(0, 1).toUpperCase()}
      </Avatar>
      <Paper
        variant="outlined"
        sx={{ p: 1.5, flex: 1, minWidth: 0, bgcolor: internal ? "#fffbeb" : "background.paper", borderColor: internal ? "#fcd34d" : "divider" }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>{comment.author?.name ?? "Unknown"}</Typography>
          {comment.author && <Typography variant="caption" color="text.secondary">{ROLE[comment.author.role]}</Typography>}
          {internal && <Chip size="small" icon={<LockOutlined />} label="Internal note" color="warning" variant="outlined" sx={{ height: 20 }} />}
          <Typography variant="caption" color="text.secondary" title={formatDateTime(comment.created_at)}>
            {formatRelative(comment.created_at)}
          </Typography>
        </Stack>
        <Typography variant="body2" sx={{ mt: 0.75, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
          {comment.content}
        </Typography>
        {comment.attachments.length > 0 && (
          <Stack spacing={0.5} sx={{ mt: 1 }}>
            {comment.attachments.map((a) => (
              <Link key={a.id} component="button" variant="body2" onClick={() => onDownload(a)} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <AttachFileOutlined fontSize="inherit" /> {a.filename} ({formatBytes(a.size_bytes)})
              </Link>
            ))}
          </Stack>
        )}
      </Paper>
    </Stack>
  );
}

export function TicketTimeline({ comments, history, onDownload }: { comments: Comment[]; history: StatusHistoryEntry[]; onDownload: (a: Attachment) => void }) {
  const items = buildTimeline(comments, history);
  return (
    <Stack spacing={1.5}>
      {items.map((item) =>
        item.kind === "comment" ? (
          <CommentBubble key={`c${item.comment.id}`} comment={item.comment} onDownload={onDownload} />
        ) : (
          <StatusEvent key={`s${item.entry.id}`} entry={item.entry} />
        ),
      )}
    </Stack>
  );
}
