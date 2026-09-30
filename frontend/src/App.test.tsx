import { ThemeProvider } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { authApi, notificationsApi, ticketsApi } from "./api/endpoints";
import type { Me } from "./api/types";
import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import { ToastProvider } from "./components/Toast";
import { theme } from "./theme";

vi.mock("./api/client", async (orig) => {
  const actual = await orig<typeof import("./api/client")>();
  return { ...actual, refreshAccessToken: vi.fn().mockResolvedValue(null) };
});

const customer: Me = {
  id: 7, name: "Rita Requester", email: "rita@acme.example.com", role: "customer", tenant_id: 1, is_active: true,
  email_verified_at: "2026-09-30T00:00:00Z", last_login_at: null, created_at: "2026-09-30T00:00:00Z",
  organization: { id: 1, name: "Acme", slug: "acme", is_demo: false },
  permissions: ["org:read", "tickets:create"], team_ids: [],
};

function renderApp(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ThemeProvider theme={theme}>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>
          <ToastProvider>
            <AuthProvider>
              <App />
            </AuthProvider>
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  // No real network in unit tests: stub the calls the app shell makes after sign-in.
  vi.spyOn(ticketsApi, "list").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  vi.spyOn(notificationsApi, "unreadCount").mockResolvedValue({ count: 0 });
});
afterEach(() => vi.restoreAllMocks());

it("sends anonymous visitors of protected pages to sign-in", async () => {
  renderApp("/dashboard");
  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

it("the landing page leads with the business problem and makes no unmeasured claims", async () => {
  renderApp("/");
  expect(await screen.findByText(/Resolve internal service requests faster/)).toBeInTheDocument();
  expect(screen.getByText(/Public demo deployment/)).toBeInTheDocument();
  // No percentages or "x faster" claims on the page until they are measured.
  expect(document.body.textContent).not.toMatch(/\d+\s?%/);
});

it("signs in and routes a requester to their tickets, hiding staff-only navigation", async () => {
  vi.spyOn(authApi, "login").mockResolvedValue({ access_token: "t", token_type: "bearer", expires_in: 900 });
  vi.spyOn(authApi, "me").mockResolvedValue(customer);
  renderApp("/login");

  await userEvent.type(await screen.findByLabelText(/Work email/), "rita@acme.example.com");
  await userEvent.type(screen.getByLabelText(/Password/), "Correct-Horse-9");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

  await waitFor(() => expect(authApi.login).toHaveBeenCalledWith("rita@acme.example.com", "Correct-Horse-9"));
  expect(await screen.findByRole("heading", { name: "My tickets" })).toBeInTheDocument();
  expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  expect(screen.queryByText("Audit log")).not.toBeInTheDocument();
});

it("shows the API's error message on failed sign-in", async () => {
  const { AxiosError, AxiosHeaders } = await import("axios");
  vi.spyOn(authApi, "login").mockRejectedValue(
    new AxiosError("x", "ERR", undefined, undefined, {
      status: 401, data: { detail: "Incorrect email or password" }, statusText: "", headers: {},
      config: { headers: new AxiosHeaders() },
    }),
  );
  renderApp("/login");
  await userEvent.type(await screen.findByLabelText(/Work email/), "x@acme.example.com");
  await userEvent.type(screen.getByLabelText(/Password/), "wrong-Password1");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("Incorrect email or password")).toBeInTheDocument();
});
