import { Alert, Button, Link, Stack, TextField } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link as RouterLink, useParams } from "react-router";

import { errorMessage } from "../../api/client";
import { authApi } from "../../api/endpoints";
import { useAuth } from "../../auth/AuthProvider";
import { Loading } from "../../components/states";
import { AuthCard } from "./AuthCard";
import { NewPasswordField, passwordProblem } from "./PasswordField";

/**
 * /register         -> create a new organization (you become its admin)
 * /join/:slug       -> join an organization's service portal as a requester
 */
export function RegisterPage() {
  const { slug } = useParams();
  const portal = useQuery({ queryKey: ["portal", slug], queryFn: () => authApi.portalInfo(slug!), enabled: !!slug, retry: false });
  const { startSession } = useAuth();
  const [form, setForm] = useState({ name: "", email: "", password: "", organization: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));

  if (slug && portal.isLoading) return <Loading />;
  if (slug && portal.isError)
    return (
      <AuthCard title="Portal not available">
        <Alert severity="warning">This organization hasn't opened self-service sign-up. Ask your IT team for an invitation.</Alert>
      </AuthCard>
    );

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const tokens = await authApi.register({
        name: form.name.trim(),
        email: form.email.trim(),
        password: form.password,
        ...(slug ? { join_slug: slug } : { organization_name: form.organization.trim() }),
      });
      // Portal requesters go straight to the request form; PublicOnly redirects.
      await startSession(tokens, slug ? "/tickets/new" : undefined);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const allowed = portal.data?.allowed_domains ?? [];
  const valid = form.name && form.email && !passwordProblem(form.password) && form.password && (slug || form.organization.trim().length >= 2);

  return (
    <AuthCard
      title={slug ? `Join ${portal.data?.name}` : "Create your organization"}
      subtitle={
        slug
          ? "Create a requester account to submit and track support requests."
          : "You'll be the organization's admin. Teams, categories and SLA policies are set up with sensible defaults."
      }
      footer={
        <>
          Already have an account? <Link component={RouterLink} to="/login">Sign in</Link>
        </>
      }
    >
      <Stack component="form" spacing={2} onSubmit={submit} noValidate>
        {error && <Alert severity="error">{error}</Alert>}
        {!slug && <TextField label="Organization name" value={form.organization} onChange={set("organization")} required autoFocus />}
        <TextField label="Your name" autoComplete="name" value={form.name} onChange={set("name")} required autoFocus={!!slug} />
        <TextField
          label="Work email"
          type="email"
          autoComplete="email"
          value={form.email}
          onChange={set("email")}
          required
          helperText={allowed.length ? `Use your ${allowed.map((d) => "@" + d).join(" or ")} address` : undefined}
        />
        <NewPasswordField label="Password" value={form.password} onChange={set("password")} required />
        <Button type="submit" variant="contained" size="large" disabled={busy || !valid}>
          {busy ? "Creating account…" : slug ? "Create account" : "Create organization"}
        </Button>
      </Stack>
    </AuthCard>
  );
}
