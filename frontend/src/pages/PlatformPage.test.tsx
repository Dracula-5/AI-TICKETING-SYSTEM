import { ThemeProvider } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { api } from "../api/client";
import { ToastProvider } from "../components/Toast";
import { theme } from "../theme";
import { PlatformPage } from "./PlatformPage";

const overview = {
  organizations: 2, demo_organizations: 1, users_by_origin: { real: 3, demo: 13 }, tickets_by_origin: { real: 4, demo: 70 },
  active_users_7d_real: 2, open_tickets: 21, tickets_7d: 9, sla_breached_open: 5,
  jobs_by_status: { done: 40, queued: 1, dead: 2 }, emails_by_status: { queued: 3 },
  ai_enabled: true, embedding_model: "sentence-transformers/all-MiniLM-L6-v2", text_generation: false,
  environment: "staging", release: "dev", background_mode: "inline", email_backend: "console",
};
const org = (over: object) => ({
  id: 1, name: "Acme", slug: "acme", is_demo: false, data_origin: "real", created_at: "2026-10-01T10:00:00Z",
  users: 3, active_users_7d: 2, tickets: 4, open_tickets: 1, tickets_7d: 2, sla_breached_open: 0,
  last_ticket_at: "2026-10-03T10:00:00Z", kb_documents: 0, ai_pending: 0, csat_average: null, csat_responses: 0, ...over,
});
const organizations = [
  org({}),
  org({ id: 2, name: "Helix Health (Demo)", slug: "helix-health-demo", is_demo: true, data_origin: "demo", users: 13, tickets: 70, csat_average: 4.25, csat_responses: 31 }),
];
const users = [
  { id: 9, name: "Platform administrator", email: "ops@example.org", role: "platform_admin", is_active: true, organization: null, data_origin: "real", created_at: "2026-10-04T10:00:00Z", last_login_at: null },
];

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ToastProvider>
            <PlatformPage />
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(api, "get").mockImplementation((url: string) => {
    const data = url.endsWith("/overview") ? overview : url.endsWith("/organizations") ? organizations : users;
    return Promise.resolve({ data });
  });
});
afterEach(() => vi.restoreAllMocks());

it("shows totals split by origin, each organization and system health", async () => {
  renderPage();
  expect(await screen.findByRole("heading", { name: "Platform console" })).toBeInTheDocument();
  expect(within(screen.getByRole("group", { name: "Users" })).getByText("3 real · 13 demo")).toBeInTheDocument();
  expect(within(screen.getByRole("group", { name: "SLA breached" })).getByText("5")).toBeInTheDocument();

  const demoRow = screen.getByRole("row", { name: /Helix Health \(Demo\)/ });
  expect(within(demoRow).getByText("Demo")).toBeInTheDocument();
  expect(within(demoRow).getByText("4.3 / 5 (31)")).toBeInTheDocument();

  expect(screen.getByText("40 done · 1 waiting or running · 2 failed")).toBeInTheDocument();
  expect(screen.getByText("Off (no provider configured)")).toBeInTheDocument();
  expect(await screen.findByText("ops@example.org")).toBeInTheDocument();
});

it("deletes an organization only after its name is typed", async () => {
  const del = vi.spyOn(api, "delete").mockResolvedValue({ data: null });
  renderPage();
  await userEvent.click(await screen.findByRole("button", { name: "Delete Acme" }));
  const dialog = screen.getByRole("dialog");
  const confirm = within(dialog).getByRole("button", { name: "Delete organization" });
  expect(confirm).toBeDisabled();
  await userEvent.type(within(dialog).getByRole("textbox"), "Acme");
  expect(confirm).toBeEnabled();
  await userEvent.click(confirm);
  expect(del).toHaveBeenCalledWith("/platform/organizations/1", { params: { confirm: "acme" } });
});
