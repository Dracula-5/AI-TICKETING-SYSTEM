import ErrorOutlineOutlined from "@mui/icons-material/ErrorOutlineOutlined";
import WarningAmberOutlined from "@mui/icons-material/WarningAmberOutlined";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Grid,
  Link,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import type { ReactNode } from "react";
import { Link as RouterLink } from "react-router";

import { analyticsApi } from "../api/endpoints";
import { AIPerformanceSection } from "./AIPerformanceSection";
import type { Overview, Priority, TicketStatus } from "../api/types";
import { BarList, ChartCard, Legend, TrendLines } from "../components/charts";
import { ErrorState, Loading, PageHeader } from "../components/states";
import { SERIES, STATUS_COLOR } from "../lib/chartTheme";
import { formatDateTime, formatMinutes } from "../lib/format";
import { PRIORITIES, PRIORITY, STATUS } from "../lib/labels";

function StatTile({ label, value, hint, to, status }: {
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

const orNA = (v: number | null, fmt: (n: number) => string) => (v === null ? "—" : fmt(v));

function Kpis({ o }: { o: Overview }) {
  const tiles = [
    { label: "Open tickets", value: o.open_tickets, to: "/tickets?view=all" },
    { label: "Created today", value: o.created_today },
    { label: "Unassigned", value: o.unassigned_open, to: "/tickets?view=queue", hint: "Open, no owner" },
    {
      label: "SLA breached",
      value: o.sla_breached_open,
      to: "/tickets?view=sla",
      hint: "Open tickets past a target",
      status: o.sla_breached_open > 0 ? ("critical" as const) : undefined,
    },
    {
      label: "SLA at risk",
      value: o.sla_at_risk_open,
      to: "/tickets?view=sla",
      hint: "Last 25% of the window",
      status: o.sla_at_risk_open > 0 ? ("warning" as const) : undefined,
    },
    { label: "Resolved", value: o.resolved_last_30d, hint: "Last 30 days" },
    { label: "Avg first response", value: orNA(o.avg_first_response_minutes_30d, formatMinutes), hint: "Tickets created in last 30 days" },
    { label: "Avg resolution time", value: orNA(o.avg_resolution_hours_30d, (h) => formatMinutes(h * 60)), hint: "Resolved in last 30 days" },
    { label: "SLA compliance", value: orNA(o.sla_compliance_pct_30d, (p) => `${p}%`), hint: "Resolved in last 30 days" },
    { label: "Reopen rate", value: orNA(o.reopen_rate_pct_30d, (p) => `${p}%`), hint: "Created in last 30 days" },
  ];
  return (
    <Grid container spacing={2} sx={{ mb: 2 }}>
      {tiles.map((t) => (
        <Grid key={t.label} size={{ xs: 6, sm: 4, md: 2.4 }}>
          <StatTile {...t} />
        </Grid>
      ))}
    </Grid>
  );
}

export function DashboardPage() {
  const overview = useQuery({
    queryKey: ["analytics", "overview"],
    queryFn: analyticsApi.overview,
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  });

  if (overview.isLoading) return <Loading />;
  if (overview.isError || !overview.data) return <ErrorState error={overview.error} onRetry={() => overview.refetch()} />;
  const o = overview.data;

  const trend = o.trend_14d.map((p) => ({ day: p.day, created: p.created, resolved: p.resolved }));
  const dayFmt = (d: string) => format(parseISO(d), "d MMM");
  const byCategory = o.by_category.map((c) => ({ name: c.key ?? "Uncategorized", value: c.count }));
  const byTeam = o.by_team.map((t) => ({ name: t.name, value: t.open }));
  const priorityCounts = new Map(o.by_priority.map((p) => [p.key, p.count]));
  const byPriority = PRIORITIES.map((p: Priority) => ({ name: PRIORITY[p].label, value: priorityCounts.get(p) ?? 0 }));

  return (
    <>
      <PageHeader
        title="Operations dashboard"
        subtitle={
          <>
            Live figures for your organization, computed from the ticket record · updated {formatDateTime(o.generated_at)}
          </>
        }
      />
      {o.data_origin !== "real" && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          These figures describe a demo organization with illustrative data. They are not production usage.
        </Alert>
      )}
      <Box sx={{ opacity: overview.isFetching ? 0.85 : 1, transition: "opacity 150ms" }}>
        <Kpis o={o} />
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, lg: 8 }}>
            <ChartCard
              title="Created vs resolved"
              subtitle="Tickets per day, last 14 days (UTC)"
              legend={<Legend items={[{ label: "Created", color: SERIES[0] }, { label: "Resolved", color: SERIES[1] }]} />}
              table={{ columns: ["Day", "Created", "Resolved"], rows: trend.map((p) => [dayFmt(p.day), p.created, p.resolved]) }}
            >
              <TrendLines
                data={trend}
                xKey="day"
                xFormat={dayFmt}
                series={[{ key: "created", label: "Created" }, { key: "resolved", label: "Resolved" }]}
              />
            </ChartCard>
          </Grid>
          <Grid size={{ xs: 12, lg: 4 }}>
            <ChartCard
              title="Open tickets by priority"
              table={{ columns: ["Priority", "Open"], rows: byPriority.map((p) => [p.name, p.value]) }}
            >
              {o.open_tickets ? <BarList data={byPriority} valueLabel="Open tickets" /> : <Typography color="text.secondary">No open tickets.</Typography>}
            </ChartCard>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <ChartCard
              title="Open tickets by category"
              table={{ columns: ["Category", "Open"], rows: byCategory.map((c) => [c.name, c.value]) }}
            >
              {byCategory.length ? <BarList data={byCategory} valueLabel="Open tickets" /> : <Typography color="text.secondary">No open tickets.</Typography>}
            </ChartCard>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <ChartCard
              title="Open tickets by team"
              table={{ columns: ["Team", "Open"], rows: byTeam.map((t) => [t.name, t.value]) }}
            >
              {byTeam.length ? <BarList data={byTeam} valueLabel="Open tickets" /> : <Typography color="text.secondary">No open tickets.</Typography>}
            </ChartCard>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Card sx={{ height: "100%" }}>
              <CardContent>
                <Typography variant="h4" component="h2" sx={{ mb: 1 }}>Workload by assignee</Typography>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Assignee</TableCell>
                      <TableCell align="right">Open tickets</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {o.by_agent.length === 0 && (
                      <TableRow><TableCell colSpan={2} sx={{ color: "text.secondary" }}>No open tickets.</TableCell></TableRow>
                    )}
                    {o.by_agent.map((a) => (
                      <TableRow key={a.id ?? "none"}>
                        <TableCell>
                          {a.id ? a.name : <Link component={RouterLink} to="/tickets?view=queue">Unassigned</Link>}
                        </TableCell>
                        <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{a.open}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Card sx={{ height: "100%" }}>
              <CardContent>
                <Typography variant="h4" component="h2" sx={{ mb: 1 }}>All tickets by status</Typography>
                <Table size="small">
                  <TableBody>
                    {o.by_status.map((s) => (
                      <TableRow key={s.key}>
                        <TableCell>{STATUS[s.key as TicketStatus]?.label ?? s.key}</TableCell>
                        <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{s.count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Box>
      <AIPerformanceSection />
    </>
  );
}
