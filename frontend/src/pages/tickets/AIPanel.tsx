import AutoAwesomeOutlined from "@mui/icons-material/AutoAwesomeOutlined";
import {
  Alert,
  Box,
  Button,
  Chip,
  Collapse,
  LinearProgress,
  Link,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link as RouterLink } from "react-router";

import { errorMessage } from "../../api/client";
import { aiApi, kbApi, orgApi } from "../../api/endpoints";
import type { AIPrediction, AIStatus, Priority, SimilarTicket, TicketDetail } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { useToast } from "../../components/Toast";
import { formatMinutes, ticketRef } from "../../lib/format";
import { AI_KIND, AI_SOURCE, AI_STATUS, PRIORITIES, PRIORITY } from "../../lib/labels";
import { DocumentDialog, HitList } from "../kb/KBComponents";

const ACTIONABLE = ["category", "priority", "team", "assignee", "duplicate", "request_info", "escalate"] as const;

export function describe(p: AIPrediction): string {
  const v = p.value;
  switch (p.kind) {
    case "category":
      return String(v.category);
    case "priority":
      return PRIORITY[v.priority as Priority]?.label ?? String(v.priority);
    case "team":
      return String(v.team);
    case "assignee":
      return String(v.name);
    case "duplicate":
      return ticketRef(Number(v.number));
    case "resolution_time":
      return `about ${formatMinutes(Number(v.hours) * 60)} (typical ${formatMinutes(Number(v.low_hours) * 60)}–${formatMinutes(Number(v.high_hours) * 60)})`;
    case "sla_risk":
      return `${Math.round(Number(v.breach_probability) * 100)}% (${v.level})`;
    case "request_info":
      return String(v.message);
    case "escalate":
      return String(v.reason);
    case "reply":
    case "summary":
      return String(v.text);
    default:
      return "";
  }
}

export function Confidence({ value }: { value: number | null }) {
  if (value == null) return null;
  const pct = Math.round(value * 100);
  return (
    <Tooltip title="Share of the similarity-weighted vote of the most similar resolved tickets. Not a guarantee.">
      <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", minWidth: 96 }}>
        <LinearProgress
          variant="determinate"
          value={pct}
          aria-label={`Confidence ${pct}%`}
          sx={{ flex: 1, height: 6, borderRadius: 3 }}
          color={value >= 0.8 ? "primary" : value >= 0.5 ? "inherit" : "warning"}
        />
        <Typography variant="caption" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums" }}>
          {pct}%
        </Typography>
      </Stack>
    </Tooltip>
  );
}

function StatusTag({ status }: { status: AIStatus }) {
  if (status === "proposed") return null;
  const meta = AI_STATUS[status];
  return <Chip size="small" label={meta.label} color={meta.tone} variant="outlined" />;
}

function SimilarList({ items }: { items: SimilarTicket[] }) {
  return (
    <Stack component="ul" spacing={0.5} sx={{ listStyle: "none", p: 0, m: 0 }}>
      {items.map((s) => (
        <Box component="li" key={s.ticket_id} sx={{ display: "flex", gap: 1, alignItems: "baseline", minWidth: 0 }}>
          <Typography variant="caption" color="text.secondary" sx={{ fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
            {Math.round(s.similarity * 100)}%
          </Typography>
          <Link component={RouterLink} to={`/tickets/${s.ticket_id}`} variant="body2" noWrap sx={{ minWidth: 0 }}>
            {ticketRef(s.number)} {s.title}
          </Link>
        </Box>
      ))}
    </Stack>
  );
}

function Recommendation({ ticket, pred }: { ticket: TicketDetail; pred: AIPrediction }) {
  const { me, can } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => orgApi.categories(), enabled: editing });
  const decide = useMutation({
    mutationFn: ({ decision, value }: { decision: "accept" | "edit" | "reject"; value?: Record<string, unknown> }) =>
      aiApi.decide(pred.id, decision, value),
    onSuccess: (_, { decision }) => {
      queryClient.invalidateQueries({ queryKey: ["ticket", ticket.id] });
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      setEditing(false);
      toast(decision === "reject" ? "Recommendation dismissed" : "Recommendation applied");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const routing = pred.kind === "team" || pred.kind === "assignee";
  const allowed = !routing || can("tickets:assign") || (pred.kind === "assignee" && pred.value.user_id === me?.id);
  const label = pred.kind === "duplicate" ? "Possible duplicate of" : AI_KIND[pred.kind];
  const editable = pred.kind === "category" || pred.kind === "priority";
  const options =
    pred.kind === "priority"
      ? PRIORITIES.map((p) => ({ value: p, label: PRIORITY[p].label }))
      : (categories.data ?? []).map((c) => ({ value: c.name, label: c.name }));

  return (
    <Box sx={{ py: 1.25, "&:not(:last-of-type)": { borderBottom: 1, borderColor: "divider" } }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between", minWidth: 0 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="caption" color="text.secondary">{label}</Typography>
          <Typography variant="body2" sx={{ fontWeight: pred.kind === "request_info" ? 400 : 600, overflowWrap: "anywhere" }}>
            {pred.kind === "duplicate" ? (
              <Link component={RouterLink} to={`/tickets/${pred.value.ticket_id}`}>{describe(pred)}</Link>
            ) : (
              describe(pred)
            )}
          </Typography>
        </Box>
        <Stack spacing={0.5} sx={{ alignItems: "flex-end", flexShrink: 0 }}>
          <Confidence value={pred.confidence} />
          <StatusTag status={pred.status} />
        </Stack>
      </Stack>
      {pred.kind === "duplicate" && pred.evidence?.candidates && (
        <Box sx={{ mt: 0.75 }}>
          <SimilarList items={pred.evidence.candidates.slice(0, 3)} />
        </Box>
      )}
      {pred.kind === "assignee" && pred.evidence?.reason && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>{pred.evidence.reason}</Typography>
      )}
      {pred.status === "proposed" && (
        <Collapse in={editing} unmountOnExit>
          <TextField
            select
            size="small"
            fullWidth
            label={`Correct ${AI_KIND[pred.kind].toLowerCase()}`}
            value=""
            sx={{ mt: 1 }}
            onChange={(e) => decide.mutate({ decision: "edit", value: { [pred.kind]: e.target.value } })}
          >
            {options.map((o) => (
              <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
            ))}
          </TextField>
        </Collapse>
      )}
      {pred.status === "proposed" && (
        <Stack direction="row" spacing={0.5} sx={{ mt: 0.75 }}>
          <Tooltip title={allowed ? "" : "Only managers can route tickets to other teams or people"}>
            <span>
              <Button size="small" variant="outlined" disabled={!allowed || decide.isPending} onClick={() => decide.mutate({ decision: "accept" })}>
                {pred.kind === "duplicate" ? "Link as duplicate" : pred.kind === "request_info" ? "Send to requester" : "Accept"}
              </Button>
            </span>
          </Tooltip>
          {editable && (
            <Button size="small" disabled={decide.isPending} onClick={() => setEditing((e) => !e)}>
              {editing ? "Cancel" : "Edit"}
            </Button>
          )}
          <Button size="small" color="inherit" disabled={decide.isPending} onClick={() => decide.mutate({ decision: "reject" })}>
            {pred.kind === "duplicate" ? "Not a duplicate" : pred.kind === "request_info" || pred.kind === "escalate" ? "Dismiss" : "Reject"}
          </Button>
        </Stack>
      )}
      {pred.status === "auto_applied" && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
          Applied automatically by your organization's AI policy. Change the field above if it is wrong.
        </Typography>
      )}
    </Box>
  );
}

export function AIPanel({ ticket }: { ticket: TicketDetail }) {
  const { can } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [showEvidence, setShowEvidence] = useState(false);
  const ai = useQuery({
    queryKey: ["ticket", ticket.id, "ai"],
    queryFn: () => aiApi.ticket(ticket.id),
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 2000 : false),
  });
  const analyze = useMutation({
    mutationFn: () => aiApi.analyze(ticket.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ticket", ticket.id] });
      toast("Recommendations refreshed");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  if (ai.isLoading || !ai.data) return null;
  if (ai.data.status === "disabled") return null;
  const preds = ai.data.predictions;
  const actionable = preds.filter((p) => (ACTIONABLE as readonly string[]).includes(p.kind));
  const risk = preds.find((p) => p.kind === "sla_risk");
  const eta = preds.find((p) => p.kind === "resolution_time");
  const next = preds.find((p) => p.kind === "next_action");
  const similar = preds.find((p) => p.evidence?.similar_tickets?.length)?.evidence;
  const open = !["resolved", "closed"].includes(ticket.status);

  return (
    <Box sx={{ border: 1, borderColor: "divider", borderRadius: 2, p: 2, mb: 2, bgcolor: "background.paper" }} component="section" aria-labelledby="ai-panel-title">
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between", mb: 0.5 }}>
        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
          <AutoAwesomeOutlined color="secondary" fontSize="small" />
          <Typography id="ai-panel-title" variant="h4">AI recommendations</Typography>
        </Stack>
        {can("tickets:work") && open && (
          <Button size="small" disabled={analyze.isPending} onClick={() => analyze.mutate()}>
            {analyze.isPending ? "Analyzing…" : "Re-analyze"}
          </Button>
        )}
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        Learned from your organization's resolved tickets. Nothing changes until someone accepts it, unless an admin enabled
        automatic application.
      </Typography>

      {ai.data.status === "pending" && (
        <Stack spacing={0.5} role="status">
          <LinearProgress />
          <Typography variant="body2" color="text.secondary">Analyzing this ticket…</Typography>
        </Stack>
      )}
      {ai.data.status === "failed" && <Alert severity="warning">Analysis failed. System rules handled triage; try Re-analyze.</Alert>}
      {ai.data.status === "ready" && actionable.length === 0 && !risk && !eta && (
        <Typography variant="body2" color="text.secondary">
          Not enough similar resolved tickets yet, so system rules decided triage on their own.
        </Typography>
      )}

      {actionable.map((p) => (
        <Recommendation key={p.id} ticket={ticket} pred={p} />
      ))}

      {(risk || eta) && open && (
        <Stack spacing={0.75} sx={{ mt: 1.5 }}>
          {risk && (
            <Tooltip title={`${risk.evidence?.method ?? ""}${risk.evidence?.n ? ` (n=${risk.evidence.n})` : ""}`}>
              <Typography variant="body2">
                <Box component="span" sx={{ color: "text.secondary" }}>SLA breach risk: </Box>
                {describe(risk)} <SourceTag source={risk.source} />
              </Typography>
            </Tooltip>
          )}
          {eta && (
            <Typography variant="body2">
              <Box component="span" sx={{ color: "text.secondary" }}>Tickets of this priority usually take </Box>
              {describe(eta)} <SourceTag source={eta.source} />
            </Typography>
          )}
        </Stack>
      )}

      {next && open && Array.isArray(next.value.steps) && next.value.steps.length > 0 && (
        <Box sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary">
            Suggested next steps <SourceTag source={next.source} />
          </Typography>
          <Box component="ol" sx={{ pl: 2.5, my: 0.5 }}>
            {(next.value.steps as string[]).map((s) => (
              <Typography component="li" variant="body2" key={s}>{s}</Typography>
            ))}
          </Box>
        </Box>
      )}

      {similar?.similar_tickets && (
        <Box sx={{ mt: 1.5 }}>
          <Link component="button" variant="caption" onClick={() => setShowEvidence((s) => !s)}>
            {showEvidence ? "Hide" : "Show"} the {similar.neighbors_used ?? similar.similar_tickets.length} similar resolved
            tickets behind this
          </Link>
          <Collapse in={showEvidence}>
            <Box sx={{ mt: 1 }}>
              <SimilarList items={similar.similar_tickets} />
            </Box>
          </Collapse>
        </Box>
      )}
      <RelatedKnowledge ticketId={ticket.id} />
      <AgentLog ticketId={ticket.id} />
      <GeneratedText ticket={ticket} predictions={preds} />
      {ai.data.model && (
        <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 1.5 }}>
          Model: {ai.data.model.split("/").pop()} ·{" "}
          <Link component={RouterLink} to="/ai-notice" color="inherit">How the AI works</Link>
        </Typography>
      )}
    </Box>
  );
}

function AgentLog({ ticketId }: { ticketId: number }) {
  const [open, setOpen] = useState(false);
  const runs = useQuery({ queryKey: ["ticket", ticketId, "agent-runs"], queryFn: () => aiApi.runs(ticketId), enabled: open });
  const run = runs.data?.[0];
  return (
    <Box sx={{ mt: 1.5 }}>
      <Link component="button" variant="caption" onClick={() => setOpen((o) => !o)}>
        {open ? "Hide" : "Show"} how the AI decided
      </Link>
      <Collapse in={open} unmountOnExit>
        {run ? (
          <Box sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              {run.planner} · {run.trigger.replace("_", " ")} · {Math.round(run.latency_ms ?? 0)} ms
            </Typography>
            <Box component="ul" sx={{ pl: 2, my: 0.5 }}>
              {run.steps.map((s, i) => (
                <Typography component="li" variant="caption" key={i} sx={{ display: "list-item" }}>
                  {AI_KIND[s.kind] ?? s.kind}: {s.outcome.replace("_", " ")}
                  {s.reason ? ` — ${s.reason}` : ""}
                </Typography>
              ))}
            </Box>
          </Box>
        ) : (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
            {runs.isLoading ? "Loading…" : "No agent run recorded yet."}
          </Typography>
        )}
      </Collapse>
    </Box>
  );
}

function RelatedKnowledge({ ticketId }: { ticketId: number }) {
  const [open, setOpen] = useState<number | null>(null);
  const related = useQuery({ queryKey: ["ticket", ticketId, "knowledge"], queryFn: () => kbApi.forTicket(ticketId), staleTime: 60_000 });
  const hits = related.data?.hits ?? [];
  if (!hits.length) return null;
  return (
    <Box sx={{ mt: 1.5 }}>
      <Typography variant="caption" color="text.secondary">Related articles</Typography>
      <Box sx={{ mt: 0.5 }}>
        <HitList hits={hits.slice(0, 3)} onOpen={setOpen} />
      </Box>
      <DocumentDialog id={open} onClose={() => setOpen(null)} />
    </Box>
  );
}

function GeneratedText({ ticket, predictions }: { ticket: TicketDetail; predictions: AIPrediction[] }) {
  const { can } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const caps = useQuery({ queryKey: ["ai", "capabilities"], queryFn: aiApi.capabilities, staleTime: 5 * 60_000 });
  const summary = predictions.find((p) => p.kind === "summary");
  const reply = predictions.find((p) => p.kind === "reply" && p.status === "proposed");
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["ticket", ticket.id] });
  const generate = useMutation({
    mutationFn: (kind: "summary" | "reply") => (kind === "summary" ? aiApi.summary(ticket.id) : aiApi.replyDraft(ticket.id)),
    onSuccess: refresh,
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const llm = !!caps.data?.text_generation;
  // Reply proposals also come from the agent's templates (no LLM needed).
  if (!can("tickets:work") || (!llm && !reply && !summary)) return null;
  const model = caps.data?.llm_model ?? null;
  return (
    <Box sx={{ mt: 2, pt: 1.5, borderTop: 1, borderColor: "divider" }}>
      {llm && (
        <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
          <Button size="small" variant="outlined" disabled={generate.isPending} onClick={() => generate.mutate("summary")}>
            {summary ? "Re-summarize" : "Summarize"}
          </Button>
          {ticket.status !== "closed" && (
            <Button size="small" variant="outlined" disabled={generate.isPending} onClick={() => generate.mutate("reply")}>
              Draft a reply
            </Button>
          )}
        </Stack>
      )}
      {generate.isPending && <LinearProgress sx={{ mb: 1 }} />}
      {summary && <SummaryBlock pred={summary} model={model} onDone={refresh} />}
      {reply && <ReplyDraft key={reply.id} pred={reply} model={model} onDone={refresh} />}
    </Box>
  );
}

function SummaryBlock({ pred, model, onDone }: { pred: AIPrediction; model: string | null; onDone: () => void }) {
  const decide = useMutation({ mutationFn: (d: "accept" | "reject") => aiApi.decide(pred.id, d), onSuccess: onDone });
  return (
    <Box sx={{ mb: 1.5 }}>
      <Typography variant="caption" color="text.secondary">
        Summary <SourceTag source="ai" />
      </Typography>
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", mt: 0.5 }}>{String(pred.value.text ?? "")}</Typography>
      <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, alignItems: "center" }}>
        <Typography variant="caption" color="text.disabled" sx={{ flex: 1 }}>
          Generated by {model ?? pred.model} — check it against the ticket.
        </Typography>
        {pred.status === "proposed" ? (
          <>
            <Button size="small" onClick={() => decide.mutate("accept")} disabled={decide.isPending}>Helpful</Button>
            <Button size="small" color="inherit" onClick={() => decide.mutate("reject")} disabled={decide.isPending}>Not helpful</Button>
          </>
        ) : (
          <StatusTag status={pred.status} />
        )}
      </Stack>
    </Box>
  );
}

function ReplyDraft({ pred, model, onDone }: { pred: AIPrediction; model: string | null; onDone: () => void }) {
  const toast = useToast();
  const original = String(pred.value.text ?? "");
  const [text, setText] = useState(original);
  const decide = useMutation({
    mutationFn: (d: "send" | "discard") =>
      d === "discard"
        ? aiApi.decide(pred.id, "reject")
        : text.trim() === original.trim()
          ? aiApi.decide(pred.id, "accept")
          : aiApi.decide(pred.id, "edit", { text }),
    onSuccess: (_, d) => {
      toast(d === "send" ? "Reply sent" : "Draft discarded");
      onDone();
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        Reply draft <SourceTag source={pred.source} /> — nothing is sent until you send it
      </Typography>
      <TextField
        multiline
        minRows={4}
        fullWidth
        value={text}
        onChange={(e) => setText(e.target.value)}
        sx={{ mt: 0.5 }}
        slotProps={{ htmlInput: { "aria-label": "Reply draft" } }}
      />
      {pred.evidence?.similar_tickets && pred.evidence.similar_tickets.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
          Grounded on resolution notes of {pred.evidence.similar_tickets.map((t) => ticketRef(t.number)).join(", ")}
        </Typography>
      )}
      <Stack direction="row" spacing={0.5} sx={{ mt: 1, alignItems: "center" }}>
        <Typography variant="caption" color="text.disabled" sx={{ flex: 1 }}>
          {pred.source === "rules" ? "Template with a matching help article" : `Generated by ${model ?? pred.model}`}
        </Typography>
        <Button size="small" color="inherit" disabled={decide.isPending} onClick={() => decide.mutate("discard")}>Discard</Button>
        <Button size="small" variant="contained" disabled={decide.isPending || !text.trim()} onClick={() => decide.mutate("send")}>
          Send as my reply
        </Button>
      </Stack>
    </Box>
  );
}

function SourceTag({ source }: { source: AIPrediction["source"] }) {
  return (
    <Chip
      size="small"
      label={AI_SOURCE[source]}
      variant="outlined"
      sx={{ height: 18, fontSize: 11, ml: 0.5, ...(source === "rules" ? { borderStyle: "dashed" } : {}) }}
    />
  );
}
