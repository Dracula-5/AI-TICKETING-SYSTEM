import AccountTreeOutlined from "@mui/icons-material/AccountTreeOutlined";
import FactCheckOutlined from "@mui/icons-material/FactCheckOutlined";
import GppGoodOutlined from "@mui/icons-material/GppGoodOutlined";
import HubOutlined from "@mui/icons-material/HubOutlined";
import InsightsOutlined from "@mui/icons-material/InsightsOutlined";
import TimerOutlined from "@mui/icons-material/TimerOutlined";
import { Alert, Box, Button, Card, CardContent, Container, Grid, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { Link as RouterLink, Navigate, useNavigate } from "react-router";

import { errorMessage } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { homePath } from "../../auth/homePath";
import { Brand } from "../../components/Brand";

const CAPABILITIES = [
  {
    icon: <AccountTreeOutlined color="primary" />,
    title: "Structured intake & triage",
    body: "Every request gets a category, priority and owning team the moment it arrives — with the reason for each decision recorded.",
  },
  {
    icon: <TimerOutlined color="primary" />,
    title: "SLA clocks that reflect reality",
    body: "First-response and resolution targets per priority, paused while waiting on the requester, with breaches escalated automatically.",
  },
  {
    icon: <HubOutlined color="primary" />,
    title: "One place to work",
    body: "Team queues, public replies and internal notes, attachments, mentions and live notifications for agents and managers.",
  },
  {
    icon: <FactCheckOutlined color="primary" />,
    title: "Human oversight by design",
    body: "Automated decisions are labelled as system rules or AI recommendations and can always be overridden — every change is audited.",
  },
  {
    icon: <InsightsOutlined color="primary" />,
    title: "Operational analytics",
    body: "Backlog, SLA risk, response and resolution times, and team workload computed live from the ticket record.",
  },
  {
    icon: <GppGoodOutlined color="primary" />,
    title: "Multi-tenant and secure",
    body: "Organization isolation enforced in every query, role-based permissions, rotating sessions and an append-only audit trail.",
  },
];

// Shared demo accounts exist only when the deployment was built with a demo
// password (see docs/runbook.md). Emails follow app/scripts/seed_demo.py.
const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD as string | undefined;
const DEMO_ACCOUNTS = [
  { label: "Manager", email: "morgan.manager@helix-health.example.com" },
  { label: "Support agent", email: "jordan.agent@helix-health.example.com" },
  { label: "Requester", email: "taylor.customer@helix-health.example.com" },
];

export function LandingPage() {
  const { status, me, login } = useAuth();
  const navigate = useNavigate();
  const [demoError, setDemoError] = useState("");
  if (status === "authenticated" && me) return <Navigate to={homePath(me)} replace />;

  const tryDemo = async (email: string) => {
    setDemoError("");
    try {
      navigate(homePath(await login(email, DEMO_PASSWORD!)));
    } catch (e) {
      setDemoError(errorMessage(e));
    }
  };

  return (
    <Box sx={{ bgcolor: "background.default", minHeight: "100vh" }}>
      <Container maxWidth="lg" sx={{ py: 2, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Brand />
        <Stack direction="row" spacing={1}>
          <Button component={RouterLink} to="/login">Sign in</Button>
          <Button component={RouterLink} to="/register" variant="contained">Create organization</Button>
        </Stack>
      </Container>

      <Container maxWidth="lg" sx={{ pt: { xs: 6, md: 10 }, pb: 6 }}>
        <Typography variant="overline" color="primary" sx={{ fontWeight: 700 }}>
          Service management platform
        </Typography>
        <Typography component="h1" sx={{ fontSize: { xs: 32, md: 44 }, fontWeight: 700, letterSpacing: "-0.02em", maxWidth: 820, lineHeight: 1.15 }}>
          Resolve internal service requests faster, with automation you can audit.
        </Typography>
        <Typography color="text.secondary" sx={{ fontSize: 18, maxWidth: 720, mt: 2 }}>
          Support teams lose time to manual triage, wrong assignments, missed SLAs and duplicate requests. NexaDesk AI
          structures intake, routes work to the right team, tracks every SLA clock and keeps a person in control of
          every automated decision.
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 4 }}>
          <Button component={RouterLink} to="/register" variant="contained" size="large">
            Start a free organization
          </Button>
          <Button component="a" href="/api/docs" size="large" variant="outlined">
            API documentation
          </Button>
        </Stack>

        {DEMO_PASSWORD && (
          <Card sx={{ mt: 5, maxWidth: 720 }}>
            <CardContent>
              <Typography variant="h3">Explore the demo organization</Typography>
              <Typography color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
                Sign in to a shared demo workspace with illustrative (not real) tickets. Settings that could affect other
                visitors are locked.
              </Typography>
              {demoError && <Alert severity="error" sx={{ mb: 2 }}>{demoError}</Alert>}
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                {DEMO_ACCOUNTS.map((a) => (
                  <Button key={a.email} variant="outlined" onClick={() => tryDemo(a.email)}>
                    Continue as {a.label}
                  </Button>
                ))}
              </Stack>
            </CardContent>
          </Card>
        )}
      </Container>

      <Container maxWidth="lg" sx={{ pb: 10 }}>
        <Grid container spacing={2}>
          {CAPABILITIES.map((c) => (
            <Grid key={c.title} size={{ xs: 12, sm: 6, md: 4 }}>
              <Card sx={{ height: "100%" }}>
                <CardContent>
                  {c.icon}
                  <Typography variant="h4" sx={{ mt: 1 }}>{c.title}</Typography>
                  <Typography color="text.secondary" sx={{ mt: 0.5 }}>{c.body}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 4 }}>
          Public demo deployment. Performance and model-quality figures are published only with the reproducible
          benchmark that produced them.
        </Typography>
      </Container>
    </Box>
  );
}
