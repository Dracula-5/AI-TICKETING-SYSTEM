import { Alert, Box, Card, CardContent, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tooltip, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { aiApi } from "../api/endpoints";
import type { AIKindStats } from "../api/types";
import { formatRelative } from "../lib/format";
import { AI_KIND } from "../lib/labels";

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);
const ms = (v: number | null) => (v === null ? "—" : `${Math.round(v)} ms`);

/** How people responded to AI recommendations — computed live from decision records. */
export function AIPerformanceSection() {
  const perf = useQuery({ queryKey: ["analytics", "ai-performance"], queryFn: () => aiApi.performance(30), refetchInterval: 60_000 });
  const monitoring = useQuery({ queryKey: ["analytics", "ai-monitoring"], queryFn: aiApi.monitoring });
  const latest = monitoring.data?.[0];
  if (!perf.data) return null;
  const p = perf.data;
  const rows: AIKindStats[] = p.by_kind.filter((k) => k.total > 0);
  const d = p.definitions;
  const header = (label: string, key?: string) => (
    <TableCell align="right">
      {key && d[key] ? (
        <Tooltip title={d[key]}>
          <Box component="span" sx={{ textDecoration: "underline dotted", cursor: "help" }}>{label}</Box>
        </Tooltip>
      ) : (
        label
      )}
    </TableCell>
  );
  return (
    <Card sx={{ mt: 2 }}>
      <CardContent>
        <Typography variant="h4" component="h2">AI recommendations — last {p.window_days} days</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          {p.tickets_analyzed} tickets analyzed · analysis latency p50 {ms(p.p50_latency_ms)}, p95 {ms(p.p95_latency_ms)}
          {p.data_origin !== "real" && " · demo organization: these reflect demo activity, not real usage"}
        </Typography>
        {latest && (
          <Alert severity={latest.status === "alert" ? "warning" : "info"} sx={{ mb: 1.5 }}>
            {latest.status === "insufficient_data"
              ? `Drift check ${formatRelative(latest.created_at)}: not enough recent tickets to compare (${latest.metrics.recent_tickets} in the last week).`
              : latest.status === "alert"
                ? `Drift check ${formatRelative(latest.created_at)}: ${latest.alerts.join("; ")}.`
                : `Drift check ${formatRelative(latest.created_at)}: new tickets look like the ones the AI learned from (category PSI ${latest.metrics.category_psi?.toFixed(2) ?? "—"}).`}
          </Alert>
        )}
        {p.text_generation.calls > 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            Text generation: {p.text_generation.calls} calls ({p.text_generation.failed_calls} failed) ·{" "}
            {(p.text_generation.input_tokens + p.text_generation.output_tokens).toLocaleString()} tokens · cost{" "}
            {p.text_generation.cost_usd === null ? "not configured" : `$${p.text_generation.cost_usd.toFixed(2)}`} · this month{" "}
            {p.text_generation.tokens_this_month.toLocaleString()} of {p.text_generation.monthly_token_budget.toLocaleString()} tokens
          </Typography>
        )}
        {rows.length === 0 ? (
          <Typography variant="body2" color="text.secondary">No recommendations yet.</Typography>
        ) : (
          <TableContainer>
            <Table size="small" aria-label="AI recommendation outcomes">
              <TableHead>
                <TableRow>
                  <TableCell>Recommendation</TableCell>
                  {header("Made")}
                  {header("Awaiting a person")}
                  {header("Accepted", "acceptance_rate")}
                  {header("Corrected or rejected", "override_rate")}
                  {header("Auto-applied")}
                  {header("Auto-applied, then reverted", "automation_false_positive_rate")}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((k) => (
                  <TableRow key={k.kind}>
                    <TableCell>{AI_KIND[k.kind] ?? k.kind}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{k.total}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{k.pending}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{pct(k.acceptance_rate)}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{pct(k.override_rate)}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{k.auto_applied + k.overridden}</TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{pct(k.automation_false_positive_rate)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
}
