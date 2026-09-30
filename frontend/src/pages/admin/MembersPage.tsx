import ContentCopyOutlined from "@mui/icons-material/ContentCopyOutlined";
import PersonAddOutlined from "@mui/icons-material/PersonAddOutlined";
import {
  Alert,
  Button,
  Card,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Stack,
  Switch,
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

import { errorMessage } from "../../api/client";
import { orgApi } from "../../api/endpoints";
import type { Role } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { ErrorState, Loading, PageHeader } from "../../components/states";
import { useToast } from "../../components/Toast";
import { formatDateTime, formatRelative } from "../../lib/format";
import { GRANTABLE_ROLES, ROLE } from "../../lib/labels";

function InviteDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const teams = useQuery({ queryKey: ["teams"], queryFn: orgApi.teams, enabled: open });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("agent");
  const [teamId, setTeamId] = useState("");
  const invite = useMutation({
    mutationFn: () => orgApi.invite({ email: email.trim(), role, team_id: teamId ? Number(teamId) : null }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["invitations"] }),
  });
  const roles = me?.role === "manager" ? (["agent", "customer", "analyst"] as Role[]) : GRANTABLE_ROLES;
  const close = () => {
    invite.reset();
    setEmail("");
    onClose();
  };
  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm">
      <DialogTitle>Invite someone</DialogTitle>
      <DialogContent>
        {invite.isSuccess ? (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="success">Invitation created for {invite.data.email}. An email was queued; you can also share this link directly:</Alert>
            <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <TextField value={invite.data.invite_url} fullWidth slotProps={{ htmlInput: { readOnly: true } }} />
              <Tooltip title="Copy link">
                <IconButton onClick={() => navigator.clipboard.writeText(invite.data.invite_url)} aria-label="Copy invitation link">
                  <ContentCopyOutlined />
                </IconButton>
              </Tooltip>
            </Stack>
            <Typography variant="caption" color="text.secondary">The link is shown only once and expires in 7 days.</Typography>
          </Stack>
        ) : (
          <Stack spacing={2} sx={{ mt: 1 }}>
            {invite.isError && <Alert severity="error">{errorMessage(invite.error)}</Alert>}
            <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
            <TextField select label="Role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {roles.map((r) => <MenuItem key={r} value={r}>{ROLE[r]}</MenuItem>)}
            </TextField>
            {role !== "customer" && role !== "analyst" && (
              <TextField select label="Team (optional)" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <MenuItem value="">No team</MenuItem>
                {teams.data?.map((t) => <MenuItem key={t.id} value={String(t.id)}>{t.name}</MenuItem>)}
              </TextField>
            )}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{invite.isSuccess ? "Done" : "Cancel"}</Button>
        {!invite.isSuccess && (
          <Button variant="contained" disabled={!email || invite.isPending} onClick={() => invite.mutate()}>Send invitation</Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

export function MembersPage() {
  const { me, can } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [inviteOpen, setInviteOpen] = useState(false);
  const members = useQuery({ queryKey: ["members", "all"], queryFn: () => orgApi.members({ include_inactive: true, page_size: 200 }) });
  const invitations = useQuery({ queryKey: ["invitations"], queryFn: orgApi.invitations });
  const manage = can("users:manage");

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { role?: Role; is_active?: boolean } }) => orgApi.updateMember(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["members"] });
      toast("Member updated");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const revoke = useMutation({
    mutationFn: orgApi.revokeInvitation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invitations"] });
      toast("Invitation revoked");
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });

  return (
    <>
      <PageHeader
        title="Users & invitations"
        subtitle="Everyone in your organization and what they can do."
        actions={<Button variant="contained" startIcon={<PersonAddOutlined />} onClick={() => setInviteOpen(true)}>Invite</Button>}
      />
      {invitations.data && invitations.data.length > 0 && (
        <Card sx={{ mb: 2 }}>
          <Typography variant="h4" sx={{ p: 2, pb: 0 }}>Pending invitations</Typography>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow><TableCell>Email</TableCell><TableCell>Role</TableCell><TableCell>Expires</TableCell><TableCell /></TableRow>
              </TableHead>
              <TableBody>
                {invitations.data.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell>{i.email}</TableCell>
                    <TableCell>{ROLE[i.role]}</TableCell>
                    <TableCell>{formatDateTime(i.expires_at)}</TableCell>
                    <TableCell align="right"><Button size="small" color="error" onClick={() => revoke.mutate(i.id)}>Revoke</Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      )}
      <Card>
        {members.isLoading && <Loading />}
        {members.isError && <ErrorState error={members.error} />}
        {members.data && (
          <TableContainer>
            <Table size="small" sx={{ minWidth: 720 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Role</TableCell>
                  <TableCell>Email verified</TableCell>
                  <TableCell>Last sign-in</TableCell>
                  <TableCell>Active</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {members.data.items.map((u) => {
                  const self = u.id === me?.id;
                  return (
                    <TableRow key={u.id} sx={{ opacity: u.is_active ? 1 : 0.55 }}>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{u.name}{self && " (you)"}</Typography>
                        <Typography variant="caption" color="text.secondary">{u.email}</Typography>
                      </TableCell>
                      <TableCell>
                        {manage && !self ? (
                          <TextField select value={u.role} onChange={(e) => update.mutate({ id: u.id, body: { role: e.target.value as Role } })} sx={{ minWidth: 190 }}>
                            {GRANTABLE_ROLES.map((r) => <MenuItem key={r} value={r}>{ROLE[r]}</MenuItem>)}
                          </TextField>
                        ) : (
                          <Chip size="small" label={ROLE[u.role]} variant="outlined" />
                        )}
                      </TableCell>
                      <TableCell>{u.email_verified_at ? "Yes" : "No"}</TableCell>
                      <TableCell>{u.last_login_at ? formatRelative(u.last_login_at) : "Never"}</TableCell>
                      <TableCell>
                        <Switch
                          checked={u.is_active}
                          disabled={!manage || self}
                          onChange={(e) => update.mutate({ id: u.id, body: { is_active: e.target.checked } })}
                          slotProps={{ input: { "aria-label": `${u.name} active` } }}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Card>
      <InviteDialog open={inviteOpen} onClose={() => setInviteOpen(false)} />
    </>
  );
}
