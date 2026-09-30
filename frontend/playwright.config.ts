import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run the real backend (fresh SQLite database, development
// mode so the email outbox is readable) behind the Vite dev server proxy.
// E2E_PYTHON points at the backend's interpreter (a venv locally, the job's
// Python in CI).
const python = process.env.E2E_PYTHON ?? "python";
const API_PORT = 8765;
const WEB_PORT = 5174;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: `${python} -c "import os; os.path.exists('e2e.db') and os.remove('e2e.db')" && ${python} -m alembic upgrade head && ${python} -m uvicorn app.main:app --port ${API_PORT}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ENVIRONMENT: "development",
        DATABASE_URL: "sqlite:///./e2e.db",
        SECRET_KEY: "e2e-only-secret-key-not-used-anywhere-else-0123456789",
        SLA_SWEEP_ENABLED: "false",
        FRONTEND_BASE_URL: `http://127.0.0.1:${WEB_PORT}`,
        ATTACHMENT_DIR: "./var/e2e-attachments",
      },
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort --host 127.0.0.1`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { VITE_API_PROXY_TARGET: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
