import { Box, Container, Link, Stack, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router";

import { Brand } from "../../components/Brand";

/** Plain-language notice of what the AI features do with people's data. */
export function AINoticePage() {
  return (
    <Box sx={{ bgcolor: "background.default", minHeight: "100vh", py: { xs: 3, md: 6 } }}>
      <Container maxWidth="md">
        <Stack spacing={3}>
          <Link component={RouterLink} to="/" underline="none" sx={{ alignSelf: "flex-start" }}>
            <Brand />
          </Link>
          <Typography variant="h1">How NexaDesk uses AI</Typography>
          <Section title="What the AI does">
            When a ticket arrives, NexaDesk compares it with tickets your organization has already resolved and suggests a
            category, priority, team and assignee, flags possible duplicates, estimates how long it may take and whether the
            service-level target is at risk, and points to help articles. Support staff see these suggestions with a
            confidence value and the similar tickets they came from.
          </Section>
          <Section title="Who decides">
            People do. Suggestions change nothing until a support agent accepts them. An administrator may let low-risk
            suggestions (category, priority, team, assignee) apply automatically above a confidence level; anything the
            requester would see — replies, questions, duplicate links, escalations — always waits for a person. Every
            automatic change is recorded as made by the AI and can be reverted.
          </Section>
          <Section title="Where your data goes">
            Suggestions and knowledge-base search run on NexaDesk's own servers with an open-source language model; ticket
            text is not sent to anyone for these. Generated text (ticket summaries, reply drafts, written answers from help
            articles) is available only if your organization's operator connects a text-generation provider. When that is
            switched on, the ticket or article text needed for the request is sent to that provider, every request is logged,
            and requesters' replies are still only sent by a person. Requesters never see internal notes in anything the AI
            drafts for them.
          </Section>
          <Section title="Limits">
            Suggestions can be wrong, especially for new kinds of problems and for organizations with little history. They
            are measured continuously (how often people accept, change or reject them), and those measurements are visible
            to your administrators.
          </Section>
          <Section title="Questions">
            Ask your organization's administrator, or use “Send feedback” in the account menu.
          </Section>
        </Stack>
      </Container>
    </Box>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box>
      <Typography variant="h3" sx={{ mb: 1 }}>{title}</Typography>
      <Typography color="text.secondary">{children}</Typography>
    </Box>
  );
}
