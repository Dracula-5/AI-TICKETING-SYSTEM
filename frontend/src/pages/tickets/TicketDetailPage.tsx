import ArrowBackOutlined from "@mui/icons-material/ArrowBackOutlined";
import AttachFileOutlined from "@mui/icons-material/AttachFileOutlined";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  Link,
  MenuItem,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link as RouterLink, useParams } from "react-router";

import { errorMessage } from "../../api/client";
import { orgApi, ticketsApi } from "../../api/endpoints";
import type { Attachment, Priority, TicketDetail, TicketStatus } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { DecisionSourceChip, PriorityChip, SlaChip, StatusChip } from "../../components/chips";
import { ErrorState, Loading } from "../../components/states";
import { useToast } from "../../components/Toast";
import { formatBytes, formatDateTime, formatDue, ticketRef } from "../../lib/format";
import { PRIORITIES, PRIORITY, STATUS, TRANSITION_ACTION } from "../../lib/labels";
import { TicketTimeline } from "./TicketTimeline";

const NEEDS_REASON: TicketStatus[] = ["waiting_for_customer", "escalated", "closed", "reopened"];
const PRIMARY_ACTIONS: TicketStatus[] = ["acknowledged", "in_progress", "resolved"];

async function download(a: Attachment) {
  const blob = await ticketsApi.download(a.id);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = a.filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.25 }}>{label}</Typography>
      <Box sx={{ typography: "body2" }}>{children}</Box>
    </Box>
  );
}

function TransitionDialog({ ticket, target, onClose }: { ticket: TicketDetail; target: TicketStatus | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      ticketsApi.transition(ticket.id, {
        to_status: target!,
        ...(target === "resolved" ? { resolution_summary: text } : { reason: text || undefined }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ticket", ticket.id] });
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      toast(`Ticket moved to ${STATUS[target!].label}`);
      setText("");
      onClose();
    },
  });
  if (!target) return null;
  const prompts: Partial<Record<TicketStatus, [string, string]>> = {
    resolved: ["Resolution summary", "What was done to fix it? The requester sees this."],
    waiting_for_customer: ["Question for the requester", "Posted as a public reply. The SLA clock pauses until they answer."],
    escalated: ["Reason for escalation", "Managers are notified with this reason."],
    closed: ["Reason for closing", "e.g. Duplicate of #123, or confirmed fixed."],
    reopened: ["Why reopen?", "Describe what is still wrong."],
  };
  const [label, help] = prompts[target] ?? ["Note (optional)", ""];
  const required = target === "resolved" || NEEDS_REASON.includes(target);
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{TRANSITION_ACTION[target] ?? STATUS[target].label}</DialogTitle>
      <DialogContent>
        {mutation.isError && <Alert severity="error" sx={{ mb: 2 }}>{errorMessage(mutation.error)}</Alert>}
        <TextField label={label} helperText={help} value={text} onChange={(e) => setText(e.target.value)} multiline minRows={3} fullWidth autoFocus sx={{ mt: 1 }} />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={mutation.isPending || (required && !text.trim())} onClick={() => mutation.mutate()}>
          Confirm
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function Composer({ ticket }: { ticket: TicketDetail }) {
  const { can } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [content, setContent] = useState("");
  const [visibility, setVisibility] = useState<"public" | "internal">("public");
  const [file, setFile] = useState<File | null>(null);
  const staff = can("comments:internal");
  const send = useMutation({
    mutationFn: async () => {
      const comment = await ticketsApi.addComment(ticket.id, content.trim(), visibility);
      if (file) await ticketsApi.upload(ticket.id, file, comment.id);
    },
    onSuccess: () => {
      setContent("");
      setFile(null);
      queryClient.invalidateQueries({ queryKey: ["ticket", ticket.id] });
      toast(visibility === "internal" ? "Internal note added" : "Reply sent");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  if (ticket.status === "closed" && !staff) return null;
  return (
    <Box sx={{ pt: 2 }}>
      {staff && (
        <ToggleButtonGroup size="small" exclusive value={visibility} onChange={(_, v) => v && setVisibility(v)} sx={{ mb: 1 }}>
          <ToggleButton value="public">Public reply</ToggleButton>
          <ToggleButton value="internal">Internal note</ToggleButton>
        </ToggleButtonGroup>
      )}
      <TextField
        multiline
        minRows={3}
        fullWidth
        placeholder={visibility === "internal" ? "Visible to support staff only. Mention colleagues with @email." : "Write a reply…"}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        sx={visibility === "internal" ? { "& .MuiOutlinedInput-root": { bgcolor: "#fffbeb" } } : undefined}
        slotProps={{ htmlInput: { "aria-label": "Comment" } }}
      />
      <Stack direction="row" spacing={1} sx={{ mt: 1, alignItems: "center", justifyContent: "space-between" }}>
        <Button size="small" component="label" startIcon={<AttachFileOutlined />}>
          {file ? file.name : "Attach"}
          <input hidden type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Button>
        <Button variant="contained" disabled={!content.trim() || send.isPending} onClick={() => send.mutate()}>
          {visibility === "internal" ? "Add note" : "Send reply"}
        </Button>
      </Stack>
    </Box>
  );
}

function AssignmentControls({ ticket }: { ticket: TicketDetail }) {
  const { me, can } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const manager = can("tickets:assign");
  const staff = useQuery({
    queryKey: ["members", "staff"],
    queryFn: () => orgApi.members({ role: "agent,manager,org_admin", page_size: 200 }),
    enabled: manager,
  });
  const teams = useQuery({ queryKey: ["teams"], queryFn: orgApi.teams, enabled: manager });
  const assign = useMutation({
    mutationFn: (body: { assignee_id: number | null; team_id?: number | null }) => ticketsApi.assign(ticket.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ticket", ticket.id] });
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      toast("Assignment updated");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  if (!ticket.can_assign) return null;

  if (!manager) {
    const mine = ticket.assignee?.id === me?.id;
    return (
      <Button size="small" variant={mine ? "text" : "outlined"} sx={{ alignSelf: "flex-start" }} onClick={() => assign.mutate({ assignee_id: mine ? null : me!.id })}>
        {mine ? "Unassign me" : "Assign to me"}
      </Button>
    );
  }
  return (
    <Stack spacing={1.5}>
      <TextField
        select
        label="Assignee"
        value={ticket.assignee?.id ?? ""}
        slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}
        onChange={(e) => assign.mutate({ assignee_id: e.target.value === "" ? null : Number(e.target.value) })}
      >
        <MenuItem value="">Unassigned</MenuItem>
        {(staff.data?.items ?? (ticket.assignee ? [ticket.assignee] : [])).map((u) => (
          <MenuItem key={u.id} value={u.id}>{u.name}</MenuItem>
        ))}
      </TextField>
      <TextField
        select
        label="Team"
        value={ticket.team?.id ?? ""}
        onChange={(e) => e.target.value !== "" && assign.mutate({ assignee_id: ticket.assignee?.id ?? null, team_id: Number(e.target.value) })}
      >
        {!ticket.team && <MenuItem value="">Unrouted</MenuItem>}
        {(teams.data ?? (ticket.team ? [ticket.team] : [])).map((t) => (
          <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>
        ))}
      </TextField>
    </Stack>
  );
}

function TriageControls({ ticket }: { ticket: TicketDetail }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => orgApi.categories() });
  const update = useMutation({
    mutationFn: (body: { priority?: Priority; category?: string }) => ticketsApi.update(ticket.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ticket", ticket.id] });
      toast("Ticket updated");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  return (
    <Stack spacing={1.5}>
      <TextField select label="Priority" value={ticket.priority} onChange={(e) => update.mutate({ priority: e.target.value as Priority })}>
        {PRIORITIES.map((p) => (
          <MenuItem key={p} value={p}>{PRIORITY[p].label}</MenuItem>
        ))}
      </TextField>
      <TextField select label="Category" value={ticket.category ?? ""} onChange={(e) => update.mutate({ category: e.target.value })}>
        {!ticket.category && <MenuItem value="">Uncategorized</MenuItem>}
        {(categories.data?.map((c) => c.name) ?? (ticket.category ? [ticket.category] : [])).map((name) => (
          <MenuItem key={name} value={name}>{name}</MenuItem>
        ))}
      </TextField>
    </Stack>
  );
}

function ResolutionPanel({ ticket }: { ticket: TicketDetail }) {
  const { me } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const confirm = useMutation({
    mutationFn: (accepted: boolean) => ticketsApi.confirmResolution(ticket.id, accepted, accepted ? undefined : reason),
    onSuccess: (_, accepted) => {
      queryClient.invalidateQueries({ queryKey: ["ticket", ticket.id] });
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      toast(accepted ? "Thanks — the ticket is closed" : "Ticket reopened");
      setRejecting(false);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  if (!ticket.resolution_summary || !["resolved", "closed"].includes(ticket.status)) return null;
  const isRequester = ticket.requester.id === me?.id;
  return (
    <Alert severity="success" sx={{ mb: 2 }}>
      <Typography variant="subtitle2">Resolution</Typography>
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{ticket.resolution_summary}</Typography>
      {ticket.status === "resolved" && isRequester && (
        <Box sx={{ mt: 1.5 }}>
          {rejecting ? (
            <Stack spacing={1}>
              <TextField label="What is still wrong?" value={reason} onChange={(e) => setReason(e.target.value)} multiline minRows={2} sx={{ bgcolor: "background.paper" }} />
              <Stack direction="row" spacing={1}>
                <Button variant="contained" color="warning" disabled={!reason.trim() || confirm.isPending} onClick={() => confirm.mutate(false)}>Reopen ticket</Button>
                <Button onClick={() => setRejecting(false)}>Cancel</Button>
              </Stack>
            </Stack>
          ) : (
            <Stack direction="row" spacing={1}>
              <Button variant="contained" color="success" disabled={confirm.isPending} onClick={() => confirm.mutate(true)}>Yes, it's fixed</Button>
              <Button color="inherit" onClick={() => setRejecting(true)}>Still not fixed</Button>
            </Stack>
          )}
        </Box>
      )}
    </Alert>
  );
}

export function TicketDetailPage() {
  const { id } = useParams();
  const ticketId = Number(id);
  const { can, me } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<TicketStatus | null>(null);
  const ticket = useQuery({ queryKey: ["ticket", ticketId], queryFn: () => ticketsApi.get(ticketId), enabled: Number.isFinite(ticketId) });
  const comments = useQuery({ queryKey: ["ticket", ticketId, "comments"], queryFn: () => ticketsApi.comments(ticketId), enabled: ticket.isSuccess });
  const history = useQuery({ queryKey: ["ticket", ticketId, "history"], queryFn: () => ticketsApi.history(ticketId), enabled: ticket.isSuccess });
  const attachments = useQuery({ queryKey: ["ticket", ticketId, "attachments"], queryFn: () => ticketsApi.attachments(ticketId), enabled: ticket.isSuccess });
  const quick = useMutation({
    mutationFn: (to: TicketStatus) => ticketsApi.transition(ticketId, { to_status: to }),
    onSuccess: (_, to) => {
      queryClient.invalidateQueries({ queryKey: ["ticket", ticketId] });
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      toast(`Ticket moved to ${STATUS[to].label}`);
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (ticket.isLoading) return <Loading />;
  if (ticket.isError || !ticket.data) return <ErrorState error={ticket.error} onRetry={() => ticket.refetch()} />;
  const t = ticket.data;
  const staff = can("tickets:work");
  const isRequester = t.requester.id === me?.id;

  // The requester confirms/rejects from the resolution panel instead.
  const actions = t.allowed_transitions.filter((s) => !(isRequester && t.status === "resolved" && (s === "closed" || s === "reopened")));
  const onDownload = (a: Attachment) => download(a).catch((e) => toast(errorMessage(e), "error"));

  return (
    <>
      <Button component={RouterLink} to="/tickets" startIcon={<ArrowBackOutlined />} size="small" sx={{ mb: 1 }}>
        Tickets
      </Button>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ mb: 2, justifyContent: "space-between", alignItems: { md: "flex-start" } }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h1" sx={{ overflowWrap: "anywhere" }}>
            <Box component="span" sx={{ color: "text.secondary", mr: 1 }}>{ticketRef(t.number)}</Box>
            {t.title}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: "wrap", gap: 1 }}>
            <StatusChip status={t.status} />
            <PriorityChip priority={t.priority} />
            {staff && <SlaChip sla={t.sla} />}
            {t.data_origin !== "real" && <Typography variant="caption" color="warning.main">Demo data</Typography>}
          </Stack>
        </Box>
        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
          {actions.map((s) => (
            <Button
              key={s}
              variant={PRIMARY_ACTIONS.includes(s) ? "contained" : "outlined"}
              color={s === "escalated" ? "error" : "primary"}
              disabled={quick.isPending}
              onClick={() => (NEEDS_REASON.includes(s) || s === "resolved" ? setTarget(s) : quick.mutate(s))}
            >
              {TRANSITION_ACTION[s] ?? STATUS[s].label}
            </Button>
          ))}
        </Stack>
      </Stack>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 8 }}>
          <ResolutionPanel ticket={t} />
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                {t.requester.name} reported · {formatDateTime(t.created_at)}
              </Typography>
              <Typography sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{t.description}</Typography>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <Typography variant="h3" sx={{ mb: 2 }}>Activity</Typography>
              {comments.isLoading || history.isLoading ? (
                <Loading />
              ) : (
                <TicketTimeline comments={comments.data ?? []} history={history.data ?? []} onDownload={onDownload} />
              )}
              <Divider sx={{ mt: 2 }} />
              <Composer ticket={t} />
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 4 }}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Stack spacing={2}>
                <Field label="Requester">{t.requester.name} <Typography component="span" variant="caption" color="text.secondary">{t.requester.email}</Typography></Field>
                <Field label="Assignee">
                  <Stack spacing={1}>
                    {!can("tickets:assign") && <span>{t.assignee?.name ?? "Unassigned"}</span>}
                    <AssignmentControls ticket={t} />
                  </Stack>
                </Field>
                {!can("tickets:assign") && <Field label="Team">{t.team?.name ?? "Unrouted"}</Field>}
                {staff && t.can_edit ? (
                  <TriageControls ticket={t} />
                ) : (
                  <Field label="Category">{t.category ?? "Uncategorized"}</Field>
                )}
                {staff && (
                  <Field label="Triage decided by">
                    <DecisionSourceChip source={t.triage_source} />
                  </Field>
                )}
              </Stack>
            </CardContent>
          </Card>

          {staff && (
            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="h4" sx={{ mb: 1.5 }}>Service level</Typography>
                <Stack spacing={1.5}>
                  <Field label="First response">
                    {t.sla.first_responded_at
                      ? `Responded ${formatDateTime(t.sla.first_responded_at)}`
                      : t.sla.first_response_due ? `Due ${formatDue(t.sla.first_response_due)}` : "—"}
                    {t.sla.first_response_breached && <Typography variant="caption" color="error.main" sx={{ display: "block" }}>Target missed</Typography>}
                  </Field>
                  <Field label="Resolution">
                    {t.resolved_at
                      ? `Resolved ${formatDateTime(t.resolved_at)}`
                      : t.sla.paused ? "Paused while waiting on the requester"
                      : t.sla.resolution_due ? `Due ${formatDue(t.sla.resolution_due)} (${formatDateTime(t.sla.resolution_due)})` : "—"}
                    {t.sla.resolution_breached && <Typography variant="caption" color="error.main" sx={{ display: "block" }}>Target missed</Typography>}
                  </Field>
                  {t.reopened_count > 0 && <Field label="Reopened">{t.reopened_count}×</Field>}
                </Stack>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent>
              <Typography variant="h4" sx={{ mb: 1 }}>Attachments</Typography>
              {attachments.data?.length ? (
                <Stack spacing={0.75}>
                  {attachments.data.map((a) => (
                    <Link key={a.id} component="button" variant="body2" onClick={() => onDownload(a)} sx={{ textAlign: "left" }}>
                      {a.filename} <Typography component="span" variant="caption" color="text.secondary">({formatBytes(a.size_bytes)})</Typography>
                    </Link>
                  ))}
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">No files attached.</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      <TransitionDialog ticket={t} target={target} onClose={() => setTarget(null)} />
    </>
  );
}
