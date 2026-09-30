import { expect, test, type Page } from "@playwright/test";

// Phone-sized viewport: the core requester flow must work without horizontal scrolling.
test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

const PASSWORD = "Mobile-Test-Pass1";
const run = Date.now().toString(36);

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test("mobile: create an organization, file a ticket, read it back", async ({ page }) => {
  await page.goto("/");
  await noHorizontalScroll(page);

  await page.goto("/register");
  await page.getByLabel("Organization name").fill(`Mobile Org ${run}`);
  await page.getByLabel("Your name").fill("Mo Bile");
  await page.getByLabel("Work email").fill(`mo.${run}@mobile.example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByRole("heading", { name: "Operations dashboard" })).toBeVisible();
  await noHorizontalScroll(page);

  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "New ticket" }).click();
  await page.getByLabel("Summary").fill("Printer on floor 2 jams on every job");
  await page.getByLabel("Details").fill("The shared printer near the kitchen jams on duplex jobs.");
  await page.getByRole("button", { name: "Submit ticket" }).click();
  await expect(page.getByRole("heading", { name: /Printer on floor 2/ })).toBeVisible();
  await noHorizontalScroll(page);
  await page.screenshot({ path: "e2e/screenshots/08-mobile-ticket.png", fullPage: true });

  await page.goto("/tickets");
  await expect(page.getByText("Printer on floor 2 jams on every job")).toBeVisible();
  await noHorizontalScroll(page);
});
