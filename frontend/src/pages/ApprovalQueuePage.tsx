import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Link,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link as RouterLink } from "react-router";

import { errorMessage } from "../api/client";
import { aiApi } from "../api/endpoints";
import { PriorityChip } from "../components/chips";
import { EmptyState, ErrorState, Loading, PageHeader } from "../components/states";
import { useToast } from "../components/Toast";
import { formatRelative, ticketRef } from "../lib/format";
import { AI_KIND, AI_SOURCE, RISK_LABEL } from "../lib/labels";
import { describe } from "./tickets/AIPanel";

type RiskFilter = "all" | "high" | "medium" | "low";

/** Recommendations waiting for a person, across all open tickets (human-in-the-loop queue). */
export function ApprovalQueuePage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [risk, setRisk] = useState<RiskFilter>("all");
  const [selected, setSelected] = useState<number[]>([]);
  const queue = useQuery({
    queryKey: ["ai", "queue", risk],
    queryFn: () => aiApi.queue({ risk: risk === "all" ? undefined : risk, limit: 100 }),
    refetchInterval: 30_000,
  });
  const decide = useMutation({
    mutationFn: ({ ids, decision }: { ids: number[]; decision: "accept" | "reject" }) => aiApi.bulkDecide(ids, decision),
    onSuccess: (r, { decision }) => {
      const failed = Object.keys(r.failed).length;
      toast(
        `${r.decided.length} ${decision === "accept" ? "applied" : "dismissed"}${failed ? `, ${failed} not allowed or no longer valid` : ""}`,
        failed ? "warning" : "success",
      );
      setSelected([]);
      queryClient.invalidateQueries({ queryKey: ["ai", "queue"] });
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  const items = queue.data?.items ?? [];
  const allIds = items.map((i) => i.prediction.id);
  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const count = (r: string) => queue.data?.by_risk[r] ?? 0;

  return (
    <>
      <PageHeader
        title="AI approvals"
        subtitle="Recommendations waiting for a person. Nothing here has changed a ticket yet."
        actions={
          selected.length > 0 ? (
            <>
              <Button variant="contained" disabled={decide.isPending} onClick={() => decide.mutate({ ids: selected, decision: "accept" })}>
                Apply {selected.length}
              </Button>
              <Button color="inherit" disabled={decide.isPending} onClick={() => decide.mutate({ ids: selected, decision: "reject" })}>
                Dismiss {selected.length}
              </Button>
            </>
          ) : undefined
        }
      />
      <Card>
        <Tabs value={risk} onChange={(_, v) => { setRisk(v); setSelected([]); }} sx={{ px: 2, borderBottom: 1, borderColor: "divider" }}>
          <Tab value="all" label={`All (${queue.data ? queue.data.total : "…"})`} />
          <Tab value="high" label={`High risk (${count("high")})`} />
          <Tab value="medium" label={`Medium (${count("medium")})`} />
          <Tab value="low" label={`Low (${count("low")})`} />
        </Tabs>
        <CardContent>
          {risk === "high" && (
            <Alert severity="info" sx={{ mb: 2 }}>
              High-risk items reach the requester or change the ticket's state (replies, requests for details, escalations,
              duplicate links). Read each one before applying.
            </Alert>
          )}
          {queue.isLoading ? (
            <Loading />
          ) : queue.isError ? (
            <ErrorState error={queue.error} onRetry={() => queue.refetch()} />
          ) : items.length === 0 ? (
            <EmptyState title="Nothing waiting" body="New recommendations appear here as tickets arrive." />
          ) : (
            <TableContainer>
              <Table size="small" aria-label="Recommendations awaiting approval">
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={selected.length === allIds.length}
                        indeterminate={selected.length > 0 && selected.length < allIds.length}
                        onChange={(e) => setSelected(e.target.checked ? allIds : [])}
                        slotProps={{ input: { "aria-label": "Select all" } }}
                      />
                    </TableCell>
                    <TableCell>Ticket</TableCell>
                    <TableCell>Recommendation</TableCell>
                    <TableCell>Risk</TableCell>
                    <TableCell align="right">Confidence</TableCell>
                    <TableCell align="right">Waiting</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((i) => {
                    const p = i.prediction;
                    const r = RISK_LABEL[i.risk];
                    return (
                      <TableRow key={p.id} hover selected={selected.includes(p.id)}>
                        <TableCell padding="checkbox">
                          <Checkbox checked={selected.includes(p.id)} onChange={() => toggle(p.id)}
                            slotProps={{ input: { "aria-label": `Select ${AI_KIND[p.kind]} for ${ticketRef(i.ticket_number)}` } }} />
                        </TableCell>
                        <TableCell sx={{ maxWidth: 280 }}>
                          <Link component={RouterLink} to={`/tickets/${i.ticket_id}`} sx={{ display: "block" }} noWrap>
                            {ticketRef(i.ticket_number)} {i.ticket_title}
                          </Link>
                          <PriorityChip priority={i.ticket_priority} />
                        </TableCell>
                        <TableCell sx={{ maxWidth: 420 }}>
                          <Typography variant="caption" color="text.secondary">
                            {AI_KIND[p.kind]} · {AI_SOURCE[p.source]}
                          </Typography>
                          <Typography variant="body2" sx={{ overflowWrap: "anywhere", display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                            {describe(p)}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Tooltip title={r.help}>
                            <Chip size="small" label={r.label} color={r.tone} variant="outlined" />
                          </Tooltip>
                        </TableCell>
                        <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
                          {p.confidence === null ? "—" : `${Math.round(p.confidence * 100)}%`}
                        </TableCell>
                        <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>{formatRelative(p.created_at)}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
          {queue.data && queue.data.total > items.length && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="caption" color="text.secondary">
                Showing the oldest {items.length} of {queue.data.total}.
              </Typography>
            </Box>
          )}
          <Stack direction="row" sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Each item is applied with your own permissions — for example, only managers can route tickets to other teams.
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </>
  );
}
