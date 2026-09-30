import { expect, test, type Browser, type Page } from "@playwright/test";

/**
 * P1 acceptance, through the UI, with three separate browser sessions:
 * an organization admin, an invited support agent and a requester who joins
 * through the self-service portal. Screenshots land in e2e/screenshots/.
 */
const PASSWORD = "Accept4nce-UI-test";
const run = Date.now().toString(36);
const ADMIN = `priya.${run}@northwind.example.com`;
const AGENT = `sam.${run}@northwind.example.com`;
const REQUESTER = `rita.${run}@northwind.example.com`;
const SHOTS = "e2e/screenshots";

async function newSession(browser: Browser) {
  const context = await browser.newContext();
  return context.newPage();
}

async function outboxToken(page: Page, email: string, marker: string) {
  const res = await page.request.get(`/api/v1/dev/outbox?to=${encodeURIComponent(email)}`);
  const items = (await res.json()) as { body_text: string }[];
  const body = items.find((i) => i.body_text.includes(marker))!.body_text;
  return body.split("token=")[1].split(/\s/)[0];
}

test("P1: register → invite → requester ticket → agent resolves → requester confirms → analytics & audit", async ({ browser }) => {
  // 1. Register an organization.
  const admin = await newSession(browser);
  await admin.goto("/");
  await expect(admin.getByRole("heading", { name: /Resolve internal service requests faster/ })).toBeVisible();
  await admin.screenshot({ path: `${SHOTS}/01-landing.png` });
  await admin.getByRole("link", { name: "Create organization" }).click();
  await admin.getByLabel("Organization name").fill(`Northwind Health ${run}`);
  await admin.getByLabel("Your name").fill("Priya Admin");
  await admin.getByLabel("Work email").fill(ADMIN);
  await admin.getByLabel("Password").fill(PASSWORD);
  await admin.getByRole("button", { name: "Create organization" }).click();
  await expect(admin.getByRole("heading", { name: "Operations dashboard" })).toBeVisible();

  // ...and verify the email address from the emailed link.
  const verifyToken = await outboxToken(admin, ADMIN, "verify-email");
  await admin.goto(`/verify-email?token=${verifyToken}`);
  await expect(admin.getByText("Your email address is verified.")).toBeVisible();

  // 2. Invite an agent into the Service Desk team.
  await admin.goto("/admin/members");
  await admin.getByRole("button", { name: "Invite" }).click();
  await admin.getByLabel("Email").fill(AGENT);
  await admin.getByLabel("Team (optional)").click();
  await admin.getByRole("option", { name: "Service Desk" }).click();
  await admin.getByRole("button", { name: "Send invitation" }).click();
  const inviteUrl = await admin.locator('input[readonly]').inputValue();
  expect(inviteUrl).toContain("/accept-invite?token=");
  await admin.screenshot({ path: `${SHOTS}/02-invitation.png` });
  await admin.getByRole("button", { name: "Done" }).click();

  // Open the requester portal for the company domain.
  await admin.goto("/admin/settings");
  await admin.getByLabel(/self-service portal/).check();
  await admin.getByLabel("Allowed email domains").fill("northwind.example.com");
  await admin.getByRole("button", { name: "Save changes" }).click();
  await expect(admin.getByText("Organization updated")).toBeVisible();
  const portalUrl = (await admin.getByText(/\/join\//).innerText()).trim();

  const agent = await newSession(browser);
  await agent.goto(new URL(inviteUrl).pathname + new URL(inviteUrl).search);
  await expect(agent.getByRole("heading", { name: /Join Northwind Health/ })).toBeVisible();
  await agent.getByLabel("Your name").fill("Sam Agent");
  await agent.getByLabel("Choose a password").fill(PASSWORD);
  await agent.getByRole("button", { name: "Accept invitation" }).click();
  await expect(agent.getByRole("heading", { name: "My work" })).toBeVisible();

  // 3. A requester joins via the portal and creates a ticket.
  const requester = await newSession(browser);
  await requester.goto(new URL(portalUrl).pathname);
  await requester.getByLabel("Your name").fill("Rita Requester");
  await requester.getByLabel("Work email").fill(REQUESTER);
  await requester.getByLabel("Password").fill(PASSWORD);
  await requester.getByRole("button", { name: "Create account" }).click();
  await expect(requester.getByRole("heading", { name: "New ticket" })).toBeVisible();
  await requester.getByLabel("Summary").fill("Cannot log in to the payroll portal");
  await requester.getByLabel("Details").fill("Since this morning the payroll login says my password is wrong.");
  await requester.screenshot({ path: `${SHOTS}/03-new-ticket.png` });
  await requester.getByRole("button", { name: "Submit ticket" }).click();
  await expect(requester.getByText("Triaged").first()).toBeVisible();
  const ticketUrl = requester.url();

  // 4. The agent picks it up from the team queue and works it.
  await agent.getByRole("link", { name: "Team queue" }).click();
  await agent.getByText("Cannot log in to the payroll portal").click();
  await expect(agent.getByText("System rule").first()).toBeVisible();
  await agent.getByRole("button", { name: "Assign to me" }).click();
  await agent.getByRole("button", { name: "Acknowledge" }).click();
  await expect(agent.getByText("Acknowledged").first()).toBeVisible();
  await agent.getByRole("button", { name: "Start work" }).click();
  await expect(agent.getByText("In progress").first()).toBeVisible();
  await agent.getByRole("button", { name: "Internal note" }).click();
  await agent.getByLabel("Comment").fill("Account locked after 5 failed attempts.");
  await agent.getByRole("button", { name: "Add note" }).click();
  await expect(agent.getByText("Account locked after 5 failed attempts.")).toBeVisible();
  await agent.getByRole("button", { name: "Ask requester" }).click();
  await agent.getByLabel("Question for the requester").fill("Please confirm your employee ID.");
  await agent.getByRole("button", { name: "Confirm" }).click();
  await expect(agent.getByText("Waiting on requester").first()).toBeVisible();
  await agent.screenshot({ path: `${SHOTS}/04-agent-ticket.png`, fullPage: true });

  // The requester sees the question but not the internal note, and replies.
  await requester.goto(ticketUrl);
  await expect(requester.getByText("Please confirm your employee ID.").first()).toBeVisible();
  await expect(requester.getByText("Account locked after 5 failed attempts.")).toHaveCount(0);
  await requester.getByLabel("Comment").fill("Employee ID 40721");
  await requester.getByRole("button", { name: "Send reply" }).click();
  await expect(requester.getByText("In progress").first()).toBeVisible();

  // The agent resolves it.
  await agent.reload();
  await agent.getByRole("button", { name: "Resolve" }).click();
  await agent.getByLabel("Resolution summary").fill("Unlocked the account and reset the password.");
  await agent.getByRole("button", { name: "Confirm" }).click();
  await expect(agent.getByText("Resolved").first()).toBeVisible();

  // 5. The requester sees the resolution and confirms it.
  await requester.reload();
  await expect(requester.getByText("Unlocked the account and reset the password.")).toBeVisible();
  await requester.screenshot({ path: `${SHOTS}/05-requester-resolution.png` });
  await requester.getByRole("button", { name: "Yes, it's fixed" }).click();
  await expect(requester.getByText("Closed").first()).toBeVisible();

  // 6. The admin sees it in analytics…
  await admin.goto("/dashboard");
  await expect(admin.getByRole("group", { name: "Resolved" })).toContainText("1");
  await expect(admin.getByRole("group", { name: "Open tickets" })).toContainText("0");
  await expect(admin.getByRole("group", { name: "SLA compliance" })).toContainText("100%");
  await admin.screenshot({ path: `${SHOTS}/06-dashboard.png`, fullPage: true });

  // 7. …and every step is in the audit log.
  await admin.goto("/audit");
  for (const action of ["ticket.create", "ticket.assign", "ticket.transition", "comment.create", "user.invite", "org.update"]) {
    await expect(admin.getByText(action, { exact: true }).first()).toBeVisible();
  }
  await admin.screenshot({ path: `${SHOTS}/07-audit-log.png` });
});
