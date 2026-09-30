import AddOutlined from "@mui/icons-material/AddOutlined";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Grid,
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
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorMessage } from "../../api/client";
import { orgApi } from "../../api/endpoints";
import type { Category, Organization, OrgSettings, SlaPolicy, Team } from "../../api/types";
import { useAuth } from "../../auth/AuthProvider";
import { ErrorState, Loading, PageHeader } from "../../components/states";
import { useToast } from "../../components/Toast";
import { formatMinutes } from "../../lib/format";
import { PRIORITY } from "../../lib/labels";

function useSaved(message: string, keys: string[][]) {
  const toast = useToast();
  const queryClient = useQueryClient();
  return {
    onSuccess: () => {
      keys.forEach((k) => queryClient.invalidateQueries({ queryKey: k }));
      toast(message);
    },
    onError: (e: unknown) => toast(errorMessage(e), "error"),
  };
}

// --- Teams ---------------------------------------------------------------------
function TeamDialog({ team, onClose }: { team: Team | "new" | null; onClose: () => void }) {
  if (!team) return null;
  return <TeamDialogForm key={team === "new" ? "new" : team.id} team={team} onClose={onClose} />;
}

function TeamDialogForm({ team, onClose }: { team: Team | "new"; onClose: () => void }) {
  const staff = useQuery({ queryKey: ["members", "staff"], queryFn: () => orgApi.members({ role: "agent,manager,org_admin", page_size: 200 }) });
  const existing = team === "new" ? null : team;
  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [members, setMembers] = useState<number[]>(existing?.member_ids ?? []);
  const saved = useSaved("Team saved", [["teams"]]);
  const save = useMutation({
    mutationFn: async () => {
      const t = team === "new" ? await orgApi.createTeam({ name, description }) : await orgApi.updateTeam((team as Team).id, { name, description });
      await orgApi.setTeamMembers(t.id, members);
    },
    ...saved,
    onSuccess: () => {
      saved.onSuccess();
      onClose();
    },
  });
  const options = staff.data?.items ?? [];
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{team === "new" ? "New team" : `Edit ${team.name}`}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {save.isError && <Alert severity="error">{errorMessage(save.error)}</Alert>}
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          <TextField label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
          <Autocomplete
            multiple
            options={options}
            getOptionLabel={(o) => o.name}
            value={options.filter((o) => members.includes(o.id))}
            onChange={(_, v) => setMembers(v.map((o) => o.id))}
            renderInput={(params) => <TextField {...params} label="Members" helperText="Only staff (agents, managers, admins) can be team members." />}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!name.trim() || save.isPending} onClick={() => save.mutate()}>Save</Button>
      </DialogActions>
    </Dialog>
  );
}

export function TeamsPage() {
  const teams = useQuery({ queryKey: ["teams"], queryFn: orgApi.teams });
  const staff = useQuery({ queryKey: ["members", "staff"], queryFn: () => orgApi.members({ role: "agent,manager,org_admin", page_size: 200 }) });
  const [editing, setEditing] = useState<Team | "new" | null>(null);
  const names = new Map(staff.data?.items.map((u) => [u.id, u.name]));
  return (
    <>
      <PageHeader title="Teams" subtitle="Groups that own tickets. Categories route new tickets to a team." actions={<Button variant="contained" startIcon={<AddOutlined />} onClick={() => setEditing("new")}>New team</Button>} />
      {teams.isLoading && <Loading />}
      {teams.isError && <ErrorState error={teams.error} />}
      <Grid container spacing={2}>
        {teams.data?.map((t) => (
          <Grid key={t.id} size={{ xs: 12, sm: 6, lg: 4 }}>
            <Card sx={{ height: "100%" }}>
              <CardContent>
                <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                  <Box>
                    <Typography variant="h4">{t.name}</Typography>
                    <Typography variant="body2" color="text.secondary">{t.description}</Typography>
                  </Box>
                  <Button size="small" onClick={() => setEditing(t)}>Edit</Button>
                </Stack>
                <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.5, mt: 1.5 }}>
                  {t.member_ids.length === 0 && <Typography variant="caption" color="text.secondary">No members yet</Typography>}
                  {t.member_ids.map((id) => <Chip key={id} size="small" label={names.get(id) ?? `User ${id}`} />)}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
      <TeamDialog team={editing} onClose={() => setEditing(null)} />
    </>
  );
}

// --- Categories -----------------------------------------------------------------
const EMPTY_CATEGORY: Omit<Category, "id"> = { name: "", description: "", keywords: [], default_team_id: null, is_active: true };

function CategoryDialog({ category, teams, onClose }: { category: Category | "new" | null; teams: Team[]; onClose: () => void }) {
  if (!category) return null;
  return <CategoryDialogForm key={category === "new" ? "new" : category.id} category={category} teams={teams} onClose={onClose} />;
}

function CategoryDialogForm({ category, teams, onClose }: { category: Category | "new"; teams: Team[]; onClose: () => void }) {
  const [form, setForm] = useState<Omit<Category, "id">>(category === "new" ? EMPTY_CATEGORY : { ...category });
  const saved = useSaved("Category saved", [["categories"]]);
  const save = useMutation({
    mutationFn: () => (category === "new" ? orgApi.createCategory(form) : orgApi.updateCategory((category as Category).id, form)),
    ...saved,
    onSuccess: () => {
      saved.onSuccess();
      onClose();
    },
  });
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{category === "new" ? "New category" : `Edit ${category.name}`}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {save.isError && <Alert severity="error">{errorMessage(save.error)}</Alert>}
          <TextField label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus />
          <TextField label="Description" value={form.description ?? ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <Autocomplete
            multiple
            freeSolo
            options={[]}
            value={form.keywords}
            onChange={(_, v) => setForm({ ...form, keywords: v as string[] })}
            renderInput={(params) => <TextField {...params} label="Rule keywords" helperText="Whole words or phrases. Press Enter after each. Used by the deterministic rules engine." />}
          />
          <TextField select label="Route to team" value={form.default_team_id ?? ""} onChange={(e) => setForm({ ...form, default_team_id: e.target.value === "" ? null : Number(e.target.value) })}>
            <MenuItem value="">No default team</MenuItem>
            {teams.map((t) => <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>)}
          </TextField>
          <FormControlLabel control={<Switch checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />} label="Active" />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!form.name.trim() || save.isPending} onClick={() => save.mutate()}>Save</Button>
      </DialogActions>
    </Dialog>
  );
}

export function CategoriesPage() {
  const categories = useQuery({ queryKey: ["categories", "all"], queryFn: () => orgApi.categories(true) });
  const teams = useQuery({ queryKey: ["teams"], queryFn: orgApi.teams });
  const [editing, setEditing] = useState<Category | "new" | null>(null);
  const teamName = new Map(teams.data?.map((t) => [t.id, t.name]));
  return (
    <>
      <PageHeader
        title="Categories & routing"
        subtitle="Your ticket taxonomy. Keywords feed the rules engine; the team is where new tickets in that category are routed."
        actions={<Button variant="contained" startIcon={<AddOutlined />} onClick={() => setEditing("new")}>New category</Button>}
      />
      <Card>
        {categories.isLoading && <Loading />}
        {categories.isError && <ErrorState error={categories.error} />}
        <TableContainer>
          <Table size="small" sx={{ minWidth: 720 }}>
            <TableHead>
              <TableRow><TableCell>Category</TableCell><TableCell>Routes to</TableCell><TableCell>Rule keywords</TableCell><TableCell>Status</TableCell><TableCell /></TableRow>
            </TableHead>
            <TableBody>
              {categories.data?.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{c.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{c.description}</Typography>
                  </TableCell>
                  <TableCell>{c.default_team_id ? teamName.get(c.default_team_id) : "—"}</TableCell>
                  <TableCell sx={{ maxWidth: 360 }}>
                    <Typography variant="caption" color="text.secondary">{c.keywords.join(", ") || "—"}</Typography>
                  </TableCell>
                  <TableCell>{c.is_active ? "Active" : "Inactive"}</TableCell>
                  <TableCell align="right"><Button size="small" onClick={() => setEditing(c)}>Edit</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>
      <CategoryDialog category={editing} teams={teams.data ?? []} onClose={() => setEditing(null)} />
    </>
  );
}

// --- SLA policies ------------------------------------------------------------------
export function SlaPoliciesPage() {
  const policies = useQuery({ queryKey: ["sla-policies"], queryFn: orgApi.slaPolicies });
  return (
    <>
      <PageHeader title="SLA policies" subtitle="Targets per priority. Changes apply to tickets created from now on; the clock pauses while waiting on the requester." />
      {policies.isLoading && <Loading />}
      {policies.isError && <ErrorState error={policies.error} />}
      {policies.data && <SlaPolicyForm key={policies.dataUpdatedAt} initial={policies.data} />}
    </>
  );
}

function SlaPolicyForm({ initial }: { initial: SlaPolicy[] }) {
  const [draft, setDraft] = useState<SlaPolicy[]>(initial);
  const save = useMutation({ mutationFn: () => orgApi.setSlaPolicies(draft), ...useSaved("SLA policies saved", [["sla-policies"]]) });
  const setMinutes = (i: number, key: "first_response_minutes" | "resolution_minutes", value: string) =>
    setDraft((d) => d.map((p, j) => (j === i ? { ...p, [key]: Number(value) } : p)));

  return (
    <>
      <Card sx={{ maxWidth: 820 }}>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow><TableCell>Priority</TableCell><TableCell>First response (minutes)</TableCell><TableCell>Resolution (minutes)</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {draft.map((p, i) => (
                <TableRow key={p.priority}>
                  <TableCell sx={{ fontWeight: 600 }}>{PRIORITY[p.priority].label}</TableCell>
                  <TableCell>
                    <TextField type="number" value={p.first_response_minutes} onChange={(e) => setMinutes(i, "first_response_minutes", e.target.value)} helperText={formatMinutes(p.first_response_minutes)} slotProps={{ htmlInput: { min: 1 } }} />
                  </TableCell>
                  <TableCell>
                    <TextField type="number" value={p.resolution_minutes} onChange={(e) => setMinutes(i, "resolution_minutes", e.target.value)} helperText={formatMinutes(p.resolution_minutes)} slotProps={{ htmlInput: { min: 1 } }} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
        <Box sx={{ p: 2, display: "flex", justifyContent: "flex-end" }}>
          <Button variant="contained" disabled={save.isPending || !draft.length} onClick={() => save.mutate()}>Save policies</Button>
        </Box>
      </Card>
    </>
  );
}

// --- Organization settings ------------------------------------------------------
const AUTO_KINDS: { kind: OrgSettings["ai_auto_apply_kinds"][number]; label: string }[] = [
  { kind: "category", label: "Category" },
  { kind: "priority", label: "Priority" },
  { kind: "team", label: "Team routing" },
  { kind: "assignee", label: "Assignee" },
];

function AIPolicyFields({ settings, onChange }: { settings: OrgSettings; onChange: (s: OrgSettings) => void }) {
  const toggle = (kind: OrgSettings["ai_auto_apply_kinds"][number], on: boolean) =>
    onChange({
      ...settings,
      ai_auto_apply_kinds: on ? [...settings.ai_auto_apply_kinds, kind] : settings.ai_auto_apply_kinds.filter((k) => k !== kind),
    });
  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 0.5 }}>AI recommendations</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        By default every AI recommendation waits for a person to accept, edit or reject it. Turn on automatic
        application only for low-risk fields, and only after the AI performance report shows a low override rate for
        your organization. Duplicate links are never applied automatically.
      </Typography>
      <Stack direction="row" sx={{ flexWrap: "wrap", gap: 1, mb: 2 }}>
        {AUTO_KINDS.map(({ kind, label }) => (
          <FormControlLabel
            key={kind}
            control={<Switch checked={settings.ai_auto_apply_kinds.includes(kind)} onChange={(e) => toggle(kind, e.target.checked)} />}
            label={`Auto-apply ${label.toLowerCase()}`}
          />
        ))}
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <TextField type="number" label="Auto-apply only at confidence ≥" value={settings.ai_auto_apply_threshold}
          slotProps={{ htmlInput: { min: 0.5, max: 1, step: 0.01 } }} fullWidth
          onChange={(e) => onChange({ ...settings, ai_auto_apply_threshold: Number(e.target.value) })} />
        <TextField type="number" label="Flag possible duplicates at similarity ≥" value={settings.ai_duplicate_threshold}
          slotProps={{ htmlInput: { min: 0.5, max: 1, step: 0.01 } }} fullWidth
          onChange={(e) => onChange({ ...settings, ai_duplicate_threshold: Number(e.target.value) })} />
        <TextField type="number" label="Similar resolved tickets needed" value={settings.ai_min_history}
          slotProps={{ htmlInput: { min: 1, max: 100 } }} fullWidth
          helperText="Below this, the rules engine decides alone"
          onChange={(e) => onChange({ ...settings, ai_min_history: Number(e.target.value) })} />
      </Stack>
      <TextField type="number" label="Monthly token budget for generated text (summaries, reply drafts)"
        value={settings.ai_llm_monthly_token_budget} sx={{ mt: 2 }} fullWidth
        slotProps={{ htmlInput: { min: 0, step: 100000 } }}
        helperText="Requests beyond the budget are refused until next month. 0 disables text generation."
        onChange={(e) => onChange({ ...settings, ai_llm_monthly_token_budget: Number(e.target.value) })} />
    </Box>
  );
}

export function OrgSettingsPage() {
  const org = useQuery({ queryKey: ["organization"], queryFn: orgApi.get });
  if (org.isLoading) return <Loading />;
  if (org.isError || !org.data) return <ErrorState error={org.error} />;
  return <OrgSettingsForm key={org.dataUpdatedAt} org={org.data} />;
}

function OrgSettingsForm({ org }: { org: Organization }) {
  const { reloadMe } = useAuth();
  const [name, setName] = useState(org.name);
  const [settings, setSettings] = useState<OrgSettings>(org.settings);
  const [domains, setDomains] = useState(org.settings.portal_allowed_domains.join(", "));
  const saved = useSaved("Organization updated", [["organization"]]);
  const save = useMutation({
    mutationFn: () =>
      orgApi.update({
        name,
        settings: { ...settings, portal_allowed_domains: domains.split(",").map((d) => d.trim()).filter(Boolean) },
      }),
    ...saved,
    onSuccess: () => {
      saved.onSuccess();
      reloadMe();
    },
  });
  const portalUrl = `${window.location.origin}/join/${org.slug}`;
  return (
    <>
      <PageHeader title="Organization" subtitle="Workflow automation and requester portal." />
      <Card sx={{ maxWidth: 820 }}>
        <CardContent>
          <Stack spacing={2.5}>
            {save.isError && <Alert severity="error">{errorMessage(save.error)}</Alert>}
            <TextField label="Organization name" value={name} onChange={(e) => setName(e.target.value)} />
            <FormControlLabel
              control={<Switch checked={settings.auto_assign} onChange={(e) => setSettings({ ...settings, auto_assign: e.target.checked })} />}
              label="Auto-assign new tickets to the least-loaded agent of the routed team (system rule)"
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField type="number" label="Auto-close resolved tickets after (days)" value={settings.auto_close_days}
                onChange={(e) => setSettings({ ...settings, auto_close_days: Number(e.target.value) })} fullWidth />
              <TextField type="number" label="Allow reopening closed tickets for (days)" value={settings.reopen_window_days}
                onChange={(e) => setSettings({ ...settings, reopen_window_days: Number(e.target.value) })} fullWidth />
            </Stack>
            <Box>
              <FormControlLabel
                control={<Switch checked={settings.portal_signup_enabled} onChange={(e) => setSettings({ ...settings, portal_signup_enabled: e.target.checked })} />}
                label="Let people create requester accounts through the self-service portal"
              />
              {settings.portal_signup_enabled && (
                <Stack spacing={2} sx={{ mt: 1 }}>
                  <TextField label="Allowed email domains" value={domains} onChange={(e) => setDomains(e.target.value)} helperText="Comma-separated, e.g. acme.com. Leave empty to allow any address." />
                  <Alert severity="info">Portal sign-up link: <strong>{portalUrl}</strong></Alert>
                </Stack>
              )}
            </Box>
            <AIPolicyFields settings={settings} onChange={setSettings} />
            <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
              <Button variant="contained" disabled={save.isPending} onClick={() => save.mutate()}>Save changes</Button>
            </Box>
          </Stack>
        </CardContent>
      </Card>
    </>
  );
}
