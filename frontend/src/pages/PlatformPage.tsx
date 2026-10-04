import DeleteOutlineOutlined from "@mui/icons-material/DeleteOutlineOutlined";
import {
  Alert,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, errorMessage } from "../api/client";
import type { Role } from "../api/types";
import { StatTile } from "../components/StatTile";
import { ErrorState, Loading, PageHeader } from "../components/states";
import { useToast } from "../components/Toast";
import { formatDateTime, formatRelative } from "../lib/format";
import { ROLE } from "../lib/labels";

interface PlatformOverview {
  organizations: number;
  demo_organizations: number;
  users_by_origin: Record<string, number>;
  tickets_by_origin: Record<string, number>;
  active_users_7d_real: number;
  open_tickets: number;
  tickets_7d: number;
  sla_breached_open: number;
  jobs_by_status: Record<string, number>;
  emails_by_status: Record<string, number>;
  ai_enabled: boolean;
  embedding_model: string | null;
  text_generation: boolean;
  environment: string;
  release: string;
  background_mode: string;
  email_backend: string;
}

interface OrganizationRow {
  id: number;
  name: string;
  slug: string;
  is_demo: boolean;
  data_origin: string;
  created_at: string;
  users: number;
  active_users_7d: number;
  tickets: number;
  open_tickets: number;
  tickets_7d: number;
  sla_breached_open: number;
  last_ticket_at: string | null;
  kb_documents: number;
  ai_pending: number;
  csat_average: number | null;
  csat_responses: number;
}

interface PlatformUser {
  id: number;
  name: string;
  email: string;
  role: Role;
  is_active: boolean;
  organization: string | null;
  data_origin: string;
  created_at: string;
  last_login_at: string | null;
}

const num = { fontVariantNumeric: "tabular-nums" } as const;
const sum = (counts: Record<string, number>) => Object.values(counts).reduce((a, b) => a + b, 0);

function DeleteOrganizationDialog({ org, onClose }: { org: OrganizationRow; onClose: () => void }) {
  const [typed, setTyped] = useState("");
  const queryClient = useQueryClient();
  const toast = useToast();
  const remove = useMutation({
    mutationFn: () => api.delete(`/platform/organizations/${org.id}`, { params: { confirm: org.slug } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["platform"] });
      toast(`Deleted ${org.name}`);
      onClose();
    },
  });
  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Delete {org.name}?</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 2 }}>
          This permanently deletes the organization with its {org.users} users, {org.tickets} tickets, articles and
          history. It cannot be undone.
        </Typography>
        {remove.isError && <Alert severity="error" sx={{ mb: 2 }}>{errorMessage(remove.error)}</Alert>}
        <TextField
          label={`Type "${org.name}" to confirm`}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          fullWidth
          autoFocus
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button color="error" variant="contained" disabled={typed.trim() !== org.name || remove.isPending} onClick={() => remove.mutate()}>
          Delete organization
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function SystemCard({ o }: { o: PlatformOverview }) {
  const failedJobs = (o.jobs_by_status.failed ?? 0) + (o.jobs_by_status.dead ?? 0);
  const rows: [string, string][] = [
    ["Environment", `${o.environment} · release ${o.release}`],
    ["AI triage", o.ai_enabled ? `On · ${o.embedding_model}` : "Off (rules only)"],
    ["Text generation", o.text_generation ? "On" : "Off (no provider configured)"],
    ["Background work", o.background_mode === "inline" ? "Inside the API process" : "Separate worker"],
    [
      "Jobs",
      `${o.jobs_by_status.done ?? 0} done · ${(o.jobs_by_status.queued ?? 0) + (o.jobs_by_status.running ?? 0)} waiting or running · ${failedJobs} failed`,
    ],
    [
      "Email",
      o.email_backend === "console"
        ? `Written to the server log only (${sum(o.emails_by_status)} messages)`
        : `${o.emails_by_status.sent ?? 0} sent · ${o.emails_by_status.queued ?? 0} queued · ${o.emails_by_status.failed ?? 0} failed`,
    ],
  ];
  return (
    <Card>
      <CardContent>
        <Typography variant="h3" sx={{ mb: 1 }}>System</Typography>
        <Table size="small">
          <TableBody>
            {rows.map(([k, v]) => (
              <TableRow key={k}>
                <TableCell sx={{ color: "text.secondary", width: 180, pl: 0 }}>{k}</TableCell>
                <TableCell>{v}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function PlatformPage() {
  const [deleting, setDeleting] = useState<OrganizationRow | null>(null);
  const overview = useQuery({
    queryKey: ["platform", "overview"],
    queryFn: () => api.get<PlatformOverview>("/platform/overview").then((r) => r.data),
    refetchInterval: 60_000,
  });
  const orgs = useQuery({
    queryKey: ["platform", "organizations"],
    queryFn: () => api.get<OrganizationRow[]>("/platform/organizations").then((r) => r.data),
    refetchInterval: 60_000,
  });
  const users = useQuery({
    queryKey: ["platform", "users"],
    queryFn: () => api.get<PlatformUser[]>("/platform/users", { params: { limit: 50 } }).then((r) => r.data),
  });

  if (overview.isLoading || orgs.isLoading) return <Loading />;
  if (overview.isError || !overview.data) return <ErrorState error={overview.error} onRetry={overview.refetch} />;
  if (orgs.isError || !orgs.data) return <ErrorState error={orgs.error} onRetry={orgs.refetch} />;
  const o = overview.data;

  const tiles = [
    { label: "Organizations", value: o.organizations, hint: `${o.demo_organizations} demo` },
    { label: "Users", value: sum(o.users_by_origin), hint: `${o.users_by_origin.real ?? 0} real · ${o.users_by_origin.demo ?? 0} demo` },
    { label: "Tickets", value: sum(o.tickets_by_origin), hint: `${o.tickets_by_origin.real ?? 0} real · ${o.tickets_by_origin.demo ?? 0} demo` },
    { label: "Open tickets", value: o.open_tickets },
    { label: "New tickets, 7 days", value: o.tickets_7d },
    {
      label: "SLA breached",
      value: o.sla_breached_open,
      hint: "Open tickets past their target",
      status: o.sla_breached_open > 0 ? ("critical" as const) : undefined,
    },
    { label: "Real users active, 7 days", value: o.active_users_7d_real, hint: "Demo accounts excluded" },
  ];

  return (
    <>
      <PageHeader
        title="Platform console"
        subtitle="Totals, activity per organization and system health. Counts only — ticket content stays inside each organization, and demo data is never counted as real usage."
      />
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {tiles.map((t) => (
          <Grid key={t.label} size={{ xs: 6, sm: 4, lg: 12 / 7 }}>
            <StatTile {...t} />
          </Grid>
        ))}
      </Grid>

      <Typography variant="h2" sx={{ mb: 1.5 }}>Organizations</Typography>
      <Card sx={{ mb: 3 }}>
        <TableContainer>
          <Table size="small" sx={{ minWidth: 1040 }}>
            <TableHead>
              <TableRow>
                <TableCell>Organization</TableCell>
                <TableCell align="right">Users</TableCell>
                <TableCell align="right">Active, 7 d</TableCell>
                <TableCell align="right">Tickets</TableCell>
                <TableCell align="right">Open</TableCell>
                <TableCell align="right">New, 7 d</TableCell>
                <TableCell align="right">SLA breached</TableCell>
                <TableCell align="right">Rating</TableCell>
                <TableCell align="right">Articles</TableCell>
                <TableCell align="right">AI to review</TableCell>
                <TableCell>Last ticket</TableCell>
                <TableCell>Created</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {orgs.data.map((org) => (
                <TableRow key={org.id} hover>
                  <TableCell>
                    <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{org.name}</Typography>
                      {org.is_demo && <Chip size="small" label="Demo" color="warning" variant="outlined" />}
                    </Stack>
                  </TableCell>
                  <TableCell align="right" sx={num}>{org.users}</TableCell>
                  <TableCell align="right" sx={num}>{org.active_users_7d}</TableCell>
                  <TableCell align="right" sx={num}>{org.tickets}</TableCell>
                  <TableCell align="right" sx={num}>{org.open_tickets}</TableCell>
                  <TableCell align="right" sx={num}>{org.tickets_7d}</TableCell>
                  <TableCell align="right" sx={num}>{org.sla_breached_open}</TableCell>
                  <TableCell align="right" sx={num}>
                    {org.csat_average === null ? "—" : `${org.csat_average.toFixed(1)} / 5 (${org.csat_responses})`}
                  </TableCell>
                  <TableCell align="right" sx={num}>{org.kb_documents}</TableCell>
                  <TableCell align="right" sx={num}>{org.ai_pending}</TableCell>
                  <TableCell>{org.last_ticket_at ? formatRelative(org.last_ticket_at) : "—"}</TableCell>
                  <TableCell>{formatDateTime(org.created_at)}</TableCell>
                  <TableCell align="right">
                    <Tooltip title="Delete organization">
                      <IconButton size="small" aria-label={`Delete ${org.name}`} onClick={() => setDeleting(org)}>
                        <DeleteOutlineOutlined fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Typography variant="h2" sx={{ mb: 1.5 }}>Health</Typography>
          <SystemCard o={o} />
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Typography variant="h2" sx={{ mb: 1.5 }}>Newest accounts</Typography>
          <Card>
            {users.isError ? (
              <ErrorState error={users.error} onRetry={users.refetch} />
            ) : (
              <TableContainer sx={{ maxHeight: 420 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>Account</TableCell>
                      <TableCell>Role</TableCell>
                      <TableCell>Organization</TableCell>
                      <TableCell>Joined</TableCell>
                      <TableCell>Last sign-in</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(users.data ?? []).map((u) => (
                      <TableRow key={u.id}>
                        <TableCell>
                          <Typography variant="body2">{u.name}</Typography>
                          <Typography variant="caption" color="text.secondary">{u.email}</Typography>
                        </TableCell>
                        <TableCell>{ROLE[u.role] ?? u.role}</TableCell>
                        <TableCell>
                          {u.organization ?? "—"}
                          {u.data_origin === "demo" && <Typography variant="caption" color="text.secondary"> · demo</Typography>}
                        </TableCell>
                        <TableCell>{formatRelative(u.created_at)}</TableCell>
                        <TableCell>{u.last_login_at ? formatRelative(u.last_login_at) : "Never"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Card>
        </Grid>
      </Grid>

      {deleting && <DeleteOrganizationDialog org={deleting} onClose={() => setDeleting(null)} />}
    </>
  );
}
