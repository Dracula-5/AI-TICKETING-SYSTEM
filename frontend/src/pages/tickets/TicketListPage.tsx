import AddOutlined from "@mui/icons-material/AddOutlined";
import SearchOutlined from "@mui/icons-material/SearchOutlined";
import {
  Box,
  Button,
  Card,
  InputAdornment,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link as RouterLink, useNavigate, useSearchParams } from "react-router";

import { orgApi, ticketsApi, type TicketQuery } from "../../api/endpoints";
import { useAuth } from "../../auth/AuthProvider";
import { PriorityChip, SlaChip, StatusChip } from "../../components/chips";
import { EmptyState, ErrorState, Loading, PageHeader } from "../../components/states";
import { formatRelative, ticketRef } from "../../lib/format";
import { PRIORITIES, PRIORITY } from "../../lib/labels";

type View = "all" | "mine" | "queue" | "sla";

const VIEWS: Record<View, { title: string; subtitle: string; base: TicketQuery }> = {
  all: { title: "All tickets", subtitle: "Every ticket in your organization.", base: {} },
  mine: { title: "My work", subtitle: "Open tickets assigned to you, most urgent first.", base: { assignee: "me", status: "open", sort: "-priority" } },
  queue: { title: "Team queue", subtitle: "Open tickets nobody has picked up yet.", base: { assignee: "unassigned", status: "open", sort: "created_at" } },
  sla: { title: "SLA monitor", subtitle: "Open tickets that are close to or past their SLA.", base: { sla: "at_risk", sort: "resolution_due" } },
};

function useDebounced<T>(value: T, ms = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function TicketListPage() {
  const { can } = useAuth();
  const [params] = useSearchParams();
  const requesterOnly = !can("tickets:read_all");
  const view: View = requesterOnly ? "all" : ((params.get("view") as View) ?? "all");
  // Keyed by view so switching views starts with fresh filters and page 1.
  return <TicketList key={view} view={view} requesterOnly={requesterOnly} />;
}

function TicketList({ view, requesterOnly }: { view: View; requesterOnly: boolean }) {
  const { can } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const meta = requesterOnly ? { title: "My tickets", subtitle: "Requests you've submitted.", base: {} } : VIEWS[view] ?? VIEWS.all;

  const [search, setSearch] = useState(params.get("q") ?? "");
  const q = useDebounced(search.trim());
  const [status, setStatus] = useState<string>("");
  const [priority, setPriority] = useState<string>("");
  const [teamId, setTeamId] = useState<string>("");
  const [slaMode, setSlaMode] = useState<"at_risk" | "breached">("at_risk");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  const query: TicketQuery = {
    ...meta.base,
    ...(status ? { status } : {}),
    ...(priority ? { priority } : {}),
    ...(teamId ? { team_id: Number(teamId) } : {}),
    ...(view === "sla" ? { sla: slaMode } : {}),
    ...(q ? { q } : {}),
    page: page + 1,
    page_size: pageSize,
  };
  const tickets = useQuery({ queryKey: ["tickets", query], queryFn: () => ticketsApi.list(query), placeholderData: keepPreviousData });
  const teams = useQuery({ queryKey: ["teams"], queryFn: orgApi.teams, enabled: can("teams:read") });

  const onSearch = (value: string) => {
    setSearch(value);
    setPage(0);
    const next = new URLSearchParams(params);
    if (value) next.set("q", value);
    else next.delete("q");
    setParams(next, { replace: true });
  };

  return (
    <>
      <PageHeader
        title={meta.title}
        subtitle={meta.subtitle}
        actions={
          can("tickets:create") && (
            <Button variant="contained" startIcon={<AddOutlined />} component={RouterLink} to="/tickets/new">
              New ticket
            </Button>
          )
        }
      />
      <Card>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ p: 2, alignItems: { md: "center" } }}>
          <TextField
            placeholder="Search title, description or #number"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            sx={{ flexGrow: 1, minWidth: 220 }}
            slotProps={{
              input: { startAdornment: <InputAdornment position="start"><SearchOutlined fontSize="small" /></InputAdornment> },
              htmlInput: { "aria-label": "Search tickets" },
            }}
          />
          {view === "sla" ? (
            <ToggleButtonGroup size="small" exclusive value={slaMode} onChange={(_, v) => v && (setSlaMode(v), setPage(0))}>
              <ToggleButton value="at_risk">At risk</ToggleButton>
              <ToggleButton value="breached">Breached</ToggleButton>
            </ToggleButtonGroup>
          ) : (
            view === "all" && (
              <TextField select label="Status" value={status} onChange={(e) => (setStatus(e.target.value), setPage(0))} sx={{ minWidth: 150 }}>
                <MenuItem value="">Any status</MenuItem>
                <MenuItem value="open">Open</MenuItem>
                <MenuItem value="done">Resolved or closed</MenuItem>
                <MenuItem value="waiting_for_customer">Waiting on requester</MenuItem>
                <MenuItem value="escalated">Escalated</MenuItem>
              </TextField>
            )
          )}
          {!requesterOnly && (
            <TextField select label="Priority" value={priority} onChange={(e) => (setPriority(e.target.value), setPage(0))} sx={{ minWidth: 130 }}>
              <MenuItem value="">Any priority</MenuItem>
              {PRIORITIES.map((p) => (
                <MenuItem key={p} value={p}>{PRIORITY[p].label}</MenuItem>
              ))}
            </TextField>
          )}
          {teams.data && (
            <TextField select label="Team" value={teamId} onChange={(e) => (setTeamId(e.target.value), setPage(0))} sx={{ minWidth: 160 }}>
              <MenuItem value="">All teams</MenuItem>
              {teams.data.map((t) => (
                <MenuItem key={t.id} value={String(t.id)}>{t.name}</MenuItem>
              ))}
            </TextField>
          )}
        </Stack>

        {tickets.isLoading && <Loading />}
        {tickets.isError && <Box sx={{ p: 2 }}><ErrorState error={tickets.error} onRetry={() => tickets.refetch()} /></Box>}
        {tickets.data && tickets.data.total === 0 && (
          <EmptyState
            title={q ? "No tickets match your search" : "Nothing here"}
            body={
              view === "mine" ? "You have no open tickets assigned. Pick one up from the team queue."
                : view === "queue" ? "Every open ticket has an owner."
                : view === "sla" ? "No open tickets in this SLA state."
                : requesterOnly ? "When you submit a request it will appear here." : undefined
            }
            action={
              requesterOnly && (
                <Button variant="contained" component={RouterLink} to="/tickets/new">Submit a request</Button>
              )
            }
          />
        )}
        {tickets.data && tickets.data.total > 0 && (
          <>
            <TableContainer>
              <Table size="small" sx={{ minWidth: requesterOnly ? 560 : 900 }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ width: 70 }}>#</TableCell>
                    <TableCell>Title</TableCell>
                    <TableCell>Status</TableCell>
                    {!requesterOnly && <TableCell>Priority</TableCell>}
                    {!requesterOnly && <TableCell>SLA</TableCell>}
                    <TableCell>Assignee</TableCell>
                    {!requesterOnly && <TableCell>Team</TableCell>}
                    <TableCell>Updated</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {tickets.data.items.map((t) => (
                    <TableRow
                      key={t.id}
                      hover
                      onClick={() => navigate(`/tickets/${t.id}`)}
                      sx={{ cursor: "pointer" }}
                      tabIndex={0}
                      onKeyDown={(e) => e.key === "Enter" && navigate(`/tickets/${t.id}`)}
                    >
                      <TableCell sx={{ color: "text.secondary" }}>{ticketRef(t.number)}</TableCell>
                      <TableCell sx={{ maxWidth: 380 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{t.title}</Typography>
                        <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block" }}>
                          {t.category ?? "Uncategorized"}
                          {!requesterOnly && ` · ${t.requester.name}`}
                        </Typography>
                      </TableCell>
                      <TableCell><StatusChip status={t.status} /></TableCell>
                      {!requesterOnly && <TableCell><PriorityChip priority={t.priority} /></TableCell>}
                      {!requesterOnly && <TableCell><SlaChip sla={t.sla} /></TableCell>}
                      <TableCell>{t.assignee?.name ?? <Typography variant="body2" color="text.disabled">Unassigned</Typography>}</TableCell>
                      {!requesterOnly && <TableCell>{t.team?.name ?? "—"}</TableCell>}
                      <TableCell sx={{ whiteSpace: "nowrap", color: "text.secondary" }}>{formatRelative(t.updated_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              component="div"
              count={tickets.data.total}
              page={page}
              rowsPerPage={pageSize}
              onPageChange={(_, p) => setPage(p)}
              onRowsPerPageChange={(e) => (setPageSize(Number(e.target.value)), setPage(0))}
              rowsPerPageOptions={[10, 25, 50, 100]}
            />
          </>
        )}
      </Card>
    </>
  );
}
