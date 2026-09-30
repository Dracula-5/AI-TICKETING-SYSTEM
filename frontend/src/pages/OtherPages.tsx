import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
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
  Typography,
} from "@mui/material";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link as RouterLink } from "react-router";

import { api, errorMessage } from "../api/client";
import { auditApi, authApi } from "../api/endpoints";
import { useAuth } from "../auth/AuthProvider";
import { EmptyState, ErrorState, Loading, PageHeader } from "../components/states";
import { useToast } from "../components/Toast";
import { formatDateTime } from "../lib/format";
import { ROLE } from "../lib/labels";
import { NewPasswordField, passwordProblem } from "./public/PasswordField";

const ACTION_GROUPS = [
  { value: "", label: "All actions" },
  { value: "auth.", label: "Authentication" },
  { value: "ticket.", label: "Tickets" },
  { value: "comment.", label: "Comments" },
  { value: "attachment.", label: "Attachments" },
  { value: "user.", label: "Users & invitations" },
  { value: "sla.", label: "SLA events" },
  { value: "org.", label: "Organization" },
];

function describeChanges(changes: Record<string, unknown> | null): string {
  if (!changes) return "";
  return Object.entries(changes)
    .map(([k, v]) => (Array.isArray(v) && v.length === 2 ? `${k}: ${JSON.stringify(v[0])} → ${JSON.stringify(v[1])}` : `${k}: ${JSON.stringify(v)}`))
    .join("; ");
}

export function AuditLogPage() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const params = { ...(action ? { action } : {}), page: page + 1, page_size: pageSize };
  const logs = useQuery({ queryKey: ["audit", params], queryFn: () => auditApi.list(params), placeholderData: keepPreviousData });

  return (
    <>
      <PageHeader title="Audit log" subtitle="Append-only record of security and workflow events in your organization." />
      <Card>
        <Box sx={{ p: 2 }}>
          <TextField select label="Filter" value={action} onChange={(e) => (setAction(e.target.value), setPage(0))} sx={{ minWidth: 220 }}>
            {ACTION_GROUPS.map((g) => <MenuItem key={g.value} value={g.value}>{g.label}</MenuItem>)}
          </TextField>
        </Box>
        {logs.isLoading && <Loading />}
        {logs.isError && <Box sx={{ p: 2 }}><ErrorState error={logs.error} /></Box>}
        {logs.data?.total === 0 && <EmptyState title="No events" />}
        {logs.data && logs.data.total > 0 && (
          <>
            <TableContainer>
              <Table size="small" sx={{ minWidth: 900 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>When</TableCell>
                    <TableCell>Actor</TableCell>
                    <TableCell>Action</TableCell>
                    <TableCell>Entity</TableCell>
                    <TableCell>Details</TableCell>
                    <TableCell>Request</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {logs.data.items.map((e) => (
                    <TableRow key={e.id}>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDateTime(e.created_at)}</TableCell>
                      <TableCell>
                        {e.actor_name ?? <Chip size="small" variant="outlined" label={e.actor_type === "system" ? "System" : e.actor_type} />}
                        {e.actor_email && <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{e.actor_email}</Typography>}
                      </TableCell>
                      <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{e.action}</TableCell>
                      <TableCell>
                        {e.entity_type === "ticket" && e.entity_id ? (
                          <RouterLink to={`/tickets/${e.entity_id}`}>ticket {e.entity_id}</RouterLink>
                        ) : (
                          e.entity_type && `${e.entity_type} ${e.entity_id ?? ""}`
                        )}
                      </TableCell>
                      <TableCell sx={{ maxWidth: 380, fontSize: 12, color: "text.secondary", overflowWrap: "anywhere" }}>{describeChanges(e.changes)}</TableCell>
                      <TableCell sx={{ fontFamily: "monospace", fontSize: 11, color: "text.secondary" }}>{e.request_id?.slice(0, 8)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              component="div"
              count={logs.data.total}
              page={page}
              rowsPerPage={pageSize}
              onPageChange={(_, p) => setPage(p)}
              onRowsPerPageChange={(e) => (setPageSize(Number(e.target.value)), setPage(0))}
              rowsPerPageOptions={[25, 50, 100, 200]}
            />
          </>
        )}
      </Card>
    </>
  );
}

export function ProfilePage() {
  const { me, reloadMe } = useAuth();
  const toast = useToast();
  const [name, setName] = useState(me?.name ?? "");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const rename = useMutation({
    mutationFn: () => authApi.updateProfile(name.trim()),
    onSuccess: () => {
      reloadMe();
      toast("Profile updated");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const password = useMutation({
    mutationFn: () => authApi.changePassword(current, next),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      toast("Password changed. Other sessions were signed out.");
    },
  });
  if (!me) return null;
  return (
    <>
      <PageHeader title="Profile & security" />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="h3" sx={{ mb: 2 }}>Profile</Typography>
              <Stack spacing={2}>
                <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
                <TextField label="Email" value={me.email} disabled />
                <TextField label="Role" value={ROLE[me.role]} disabled />
                <TextField label="Organization" value={me.organization?.name ?? "—"} disabled />
                <Button variant="contained" sx={{ alignSelf: "flex-end" }} disabled={!name.trim() || name === me.name || rename.isPending} onClick={() => rename.mutate()}>
                  Save
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="h3" sx={{ mb: 2 }}>Change password</Typography>
              <Stack spacing={2}>
                {password.isError && <Alert severity="error">{errorMessage(password.error)}</Alert>}
                <TextField label="Current password" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
                <NewPasswordField label="New password" value={next} onChange={(e) => setNext(e.target.value)} />
                <Button variant="contained" sx={{ alignSelf: "flex-end" }} disabled={!current || !next || !!passwordProblem(next) || password.isPending} onClick={() => password.mutate()}>
                  Change password
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}

interface PlatformOverview {
  organizations: number;
  demo_organizations: number;
  users_by_origin: Record<string, number>;
  tickets_by_origin: Record<string, number>;
  active_users_7d_real: number;
}

export function PlatformPage() {
  const overview = useQuery({ queryKey: ["platform"], queryFn: () => api.get<PlatformOverview>("/platform/overview").then((r) => r.data) });
  if (overview.isLoading) return <Loading />;
  if (overview.isError || !overview.data) return <ErrorState error={overview.error} />;
  const o = overview.data;
  const rows: [string, number | string][] = [
    ["Organizations", o.organizations],
    ["Demo organizations", o.demo_organizations],
    ["Users (real)", o.users_by_origin.real ?? 0],
    ["Users (demo)", o.users_by_origin.demo ?? 0],
    ["Tickets (real)", o.tickets_by_origin.real ?? 0],
    ["Tickets (demo)", o.tickets_by_origin.demo ?? 0],
    ["Real users active in last 7 days", o.active_users_7d_real],
  ];
  return (
    <>
      <PageHeader title="Platform overview" subtitle="Aggregate counts across organizations, split by data origin. Demo data is never counted as real usage." />
      <Card sx={{ maxWidth: 560 }}>
        <Table>
          <TableBody>
            {rows.map(([k, v]) => (
              <TableRow key={k}><TableCell>{k}</TableCell><TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>{v}</TableCell></TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}

export function NotFoundPage() {
  return <EmptyState title="Page not found" body="The page you were looking for doesn't exist or you don't have access to it." action={<Button component={RouterLink} to="/">Go home</Button>} />;
}
