import { Alert, Button, Link, Stack, TextField } from "@mui/material";
import { useState, type FormEvent } from "react";
import { Link as RouterLink, useLocation } from "react-router";

import { errorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { AuthCard } from "./AuthCard";

export function LoginPage() {
  const { login } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const from = (location.state as { from?: string } | null)?.from;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      // The PublicOnly guard redirects once the session exists.
      await login(email.trim(), password, from);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title="Sign in"
      subtitle="Welcome back to NexaDesk AI."
      footer={
        <>
          New here? <Link component={RouterLink} to="/register">Create an organization</Link>
        </>
      }
    >
      <Stack component="form" spacing={2} onSubmit={submit} noValidate>
        {error && <Alert severity="error">{error}</Alert>}
        <TextField label="Work email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        <TextField label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <Button type="submit" variant="contained" size="large" disabled={busy || !email || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
        <Link component={RouterLink} to="/forgot-password" variant="body2" sx={{ alignSelf: "center" }}>
          Forgot your password?
        </Link>
      </Stack>
    </AuthCard>
  );
}
