import { expect, test, type Browser } from "@playwright/test";

/**
 * P5–P8 through the UI: an admin publishes a help article; a requester is
 * offered it while writing a ticket and files anyway; the admin sees the AI
 * panel on the ticket (related article, templated reply proposal) and works
 * the approval queue. The backend runs the deterministic test embedder (see
 * playwright.config.ts) — this checks behaviour, not model quality.
 */
const PASSWORD = "Accept4nce-UI-test";
const run = Date.now().toString(36);
const ADMIN = `ada.${run}@contoso.example.com`;
const REQUESTER = `ravi.${run}@contoso.example.com`;
const SHOTS = "e2e/screenshots";

const ARTICLE = `# VPN keeps disconnecting on home wifi

If the VPN client drops the tunnel every few minutes on home wifi, update the VPN client to the latest version
and turn off wifi power saving in the network adapter settings. The VPN tunnel then stays connected.
`;

async function session(browser: Browser) {
  return (await browser.newContext()).newPage();
}

test("AI assist: article suggestion, AI panel, approval queue", async ({ browser }) => {
  const admin = await session(browser);
  await admin.goto("/register");
  await admin.getByLabel("Organization name").fill(`Contoso IT ${run}`);
  await admin.getByLabel("Your name").fill("Ada Admin");
  await admin.getByLabel("Work email").fill(ADMIN);
  await admin.getByLabel("Password").fill(PASSWORD);
  await admin.getByRole("button", { name: "Create organization" }).click();
  await expect(admin.getByRole("heading", { name: "Operations dashboard" })).toBeVisible();

  // Publish a help article.
  await admin.goto("/kb");
  await admin.getByRole("button", { name: "Add article" }).click();
  await admin.locator('input[type="file"]').setInputFiles({ name: "vpn.md", mimeType: "text/markdown", buffer: Buffer.from(ARTICLE) });
  await admin.getByLabel("Who can read it").click();
  await admin.getByRole("option", { name: /Everyone in the organization/ }).click();
  await admin.getByRole("button", { name: "Upload" }).click();
  await expect(admin.getByText("ready")).toBeVisible({ timeout: 30_000 });
  await admin.getByLabel("Search the knowledge base").fill("VPN disconnecting on wifi");
  await admin.getByRole("button", { name: "Search" }).click();
  await expect(admin.getByRole("button", { name: /VPN keeps disconnecting on home wifi/ }).first()).toBeVisible();
  await admin.screenshot({ path: `${SHOTS}/10-knowledge-base.png`, fullPage: true });

  // Open the portal so a requester can join.
  await admin.goto("/admin/settings");
  await admin.getByLabel(/self-service portal/).check();
  await admin.getByLabel("Allowed email domains").fill("contoso.example.com");
  await admin.getByRole("button", { name: "Save changes" }).click();
  await expect(admin.getByText("Organization updated")).toBeVisible();
  const portalUrl = (await admin.getByText(/\/join\//).innerText()).trim();

  // The requester is offered the article while writing, then files anyway.
  const requester = await session(browser);
  await requester.goto(new URL(portalUrl).pathname);
  await requester.getByLabel("Your name").fill("Ravi Requester");
  await requester.getByLabel("Work email").fill(REQUESTER);
  await requester.getByLabel("Password").fill(PASSWORD);
  await requester.getByRole("button", { name: "Create account" }).click();
  await requester.getByRole("link", { name: "New ticket" }).click();
  await requester.getByLabel("Summary").fill("VPN keeps disconnecting on home wifi");
  await requester.getByLabel("Details").fill("The VPN client drops the tunnel every few minutes when I work from home on wifi.");
  await expect(requester.getByText("These articles might solve it right away")).toBeVisible({ timeout: 15_000 });
  await requester.screenshot({ path: `${SHOTS}/11-article-suggestion.png`, fullPage: true });
  await requester.getByRole("button", { name: "Submit ticket" }).click();
  await expect(requester.getByText(/Ticket #\d+ created/)).toBeVisible();
  const ticketPath = new URL(requester.url()).pathname;

  // Staff see the AI panel: related article and a templated reply proposal.
  await admin.goto(ticketPath);
  await expect(admin.getByRole("heading", { name: "AI recommendations" })).toBeVisible();
  await expect(admin.getByText("Related articles")).toBeVisible({ timeout: 30_000 });
  await expect(admin.getByLabel("Reply draft")).toContainText("VPN keeps disconnecting on home wifi");
  await admin.screenshot({ path: `${SHOTS}/12-ai-panel.png`, fullPage: true });

  // The approval queue lists it; dismiss it there.
  await admin.goto("/ai/approvals");
  await expect(admin.getByRole("heading", { name: "AI approvals" })).toBeVisible();
  const row = admin.getByRole("row", { name: /Reply draft/ });
  await expect(row).toBeVisible();
  await admin.screenshot({ path: `${SHOTS}/13-approval-queue.png`, fullPage: true });
  await row.getByRole("checkbox").check();
  await admin.getByRole("button", { name: "Dismiss 1" }).click();
  await expect(admin.getByText(/1 dismissed/)).toBeVisible();
});
