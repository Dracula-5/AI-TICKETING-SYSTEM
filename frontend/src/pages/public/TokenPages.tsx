import { Alert, Button, Link, Stack, TextField } from "@mui/material";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate, useSearchParams } from "react-router";

import { errorMessage } from "../../api/client";
import { authApi } from "../../api/endpoints";
import { useAuth } from "../../auth/AuthProvider";
import { homePath } from "../../auth/homePath";
import { Loading } from "../../components/states";
import { ROLE } from "../../lib/labels";
import { AuthCard } from "./AuthCard";
import { NewPasswordField, passwordProblem } from "./PasswordField";

export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const preview = useQuery({ queryKey: ["invite", token], queryFn: () => authApi.previewInvitation(token), enabled: !!token, retry: false });
  const { startSession } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const accept = useMutation({
    mutationFn: () => authApi.acceptInvitation(token, name.trim(), password),
    onSuccess: async (tokens) => navigate(homePath(await startSession(tokens)), { replace: true }),
  });

  if (!token || preview.isError)
    return (
      <AuthCard title="Invitation not valid">
        <Alert severity="warning">This invitation link is invalid, already used, or expired. Ask your administrator to send a new one.</Alert>
      </AuthCard>
    );
  if (preview.isLoading || !preview.data) return <Loading />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    accept.mutate();
  };
  return (
    <AuthCard
      title={`Join ${preview.data.organization_name}`}
      subtitle={`${preview.data.invited_by} invited ${preview.data.email} as ${ROLE[preview.data.role]}.`}
    >
      <Stack component="form" spacing={2} onSubmit={submit} noValidate>
        {accept.isError && <Alert severity="error">{errorMessage(accept.error)}</Alert>}
        <TextField label="Your name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        <NewPasswordField label="Choose a password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <Button type="submit" variant="contained" size="large" disabled={accept.isPending || !name || !password || !!passwordProblem(password)}>
          {accept.isPending ? "Joining…" : "Accept invitation"}
        </Button>
      </Stack>
    </AuthCard>
  );
}

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const verify = useMutation({ mutationFn: () => authApi.verifyEmail(token) });
  const started = useRef(false);
  useEffect(() => {
    if (token && !started.current) {
      started.current = true;
      verify.mutate();
    }
  }, [token, verify]);

  return (
    <AuthCard title="Email verification">
      {verify.isPending && <Loading label="Verifying…" />}
      {verify.isSuccess && <Alert severity="success">Your email address is verified.</Alert>}
      {(verify.isError || !token) && <Alert severity="error">{token ? errorMessage(verify.error) : "The link is incomplete."}</Alert>}
      <Button component={RouterLink} to="/login" sx={{ mt: 2 }}>
        Continue
      </Button>
    </AuthCard>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const send = useMutation({ mutationFn: () => authApi.forgotPassword(email.trim()) });
  return (
    <AuthCard
      title="Reset your password"
      subtitle="Enter your account email and we'll send you a reset link."
      footer={<Link component={RouterLink} to="/login">Back to sign in</Link>}
    >
      {send.isSuccess ? (
        <Alert severity="success">If an account exists for {email}, a reset link is on its way. It expires in 30 minutes.</Alert>
      ) : (
        <Stack component="form" spacing={2} onSubmit={(e) => { e.preventDefault(); send.mutate(); }} noValidate>
          {send.isError && <Alert severity="error">{errorMessage(send.error)}</Alert>}
          <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          <Button type="submit" variant="contained" disabled={send.isPending || !email}>
            Send reset link
          </Button>
        </Stack>
      )}
    </AuthCard>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const reset = useMutation({ mutationFn: () => authApi.resetPassword(token, password) });
  return (
    <AuthCard title="Choose a new password" footer={<Link component={RouterLink} to="/login">Back to sign in</Link>}>
      {reset.isSuccess ? (
        <Stack spacing={2}>
          <Alert severity="success">Password updated. All other sessions were signed out.</Alert>
          <Button component={RouterLink} to="/login" variant="contained">Sign in</Button>
        </Stack>
      ) : (
        <Stack component="form" spacing={2} onSubmit={(e) => { e.preventDefault(); reset.mutate(); }} noValidate>
          {reset.isError && <Alert severity="error">{errorMessage(reset.error)}</Alert>}
          <NewPasswordField label="New password" value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus />
          <Button type="submit" variant="contained" disabled={reset.isPending || !token || !password || !!passwordProblem(password)}>
            Update password
          </Button>
        </Stack>
      )}
    </AuthCard>
  );
}
