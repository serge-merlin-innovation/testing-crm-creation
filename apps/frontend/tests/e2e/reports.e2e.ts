import { expect, test, type Browser, type Page } from "@playwright/test";
import { LOGIN_PATH } from "@/lib/auth-routing";
import { ADMIN, inviteUser, signIn, signInApi, runId } from "./identities";
import { currentCode } from "./totp";

const PARTNER = {
  firstName: "Pieter",
  lastName: "Partner",
  email: "e2e.partner@example.com",
  password: "Copper-Meadow-42-Signal",
};
const BACK_OFFICE = {
  firstName: "Bea",
  lastName: "Backoffice",
  email: "e2e.backoffice@example.com",
  password: "Ledger-Harbour-58-Quill",
};
const READER = {
  firstName: "Rita",
  lastName: "Reader",
  email: "e2e.readonly@example.com",
  password: "Granite-Orchard-31-Beacon",
};
const NEWCOMER = {
  firstName: "Nina",
  lastName: "Newcomer",
  email: `e2e.newcomer.${runId()}@example.com`,
  password: "Silver-Compass-64-Meadow",
};
const RUN = runId();
const reversed = (text: string) => text.split("").reverse().join("");

/** A partner-led deal with fees, a close forecast, a milestone this month and a task this week. */
async function seed(browser: Browser) {
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const adminHeaders = await signInApi(admin, ADMIN);
  await inviteUser(browser, admin, adminHeaders, PARTNER, "Partner");
  await inviteUser(browser, admin, adminHeaders, BACK_OFFICE, "Compliance / Back-office");
  await inviteUser(browser, admin, adminHeaders, READER, "Read-only");
  await inviteUser(browser, admin, adminHeaders, NEWCOMER, "Analyst / Associate");
  const sector = await admin.post("/api/v1/picklists/", {
    headers: adminHeaders,
    data: { kind: "sector", code: `rep-${RUN}`, label_en: `Report sector ${RUN}` },
  });
  expect(sector.status(), await sector.text()).toBe(201);
  const sectorId = (await sector.json()).id as number;
  await adminContext.close();

  const context = await browser.newContext();
  const request = context.request;
  const headers = await signInApi(request, PARTNER);
  const partner: { id: number } = await (await request.get("/api/v1/users/me")).json();
  const countries: { id: number; code: string }[] = await (await request.get("/api/v1/picklists/?kind=country")).json();
  const company = await request.post("/api/v1/companies/", {
    headers,
    data: {
      // Random tokens only: a client name shared with another run's deal is a potential conflict (AUTHZ-05 c1),
      // which would hold this deal in Conflict review.
      name: `Client ${runId()}`,
      type: "target",
      country_id: countries.find((country) => country.code === "NL")!.id,
      vat_or_registry_number: `NLR-${RUN}`,
      ignore_similar: true,
    },
  });
  expect(company.status(), await company.text()).toBe(201);
  const mandate = await request.post("/api/v1/mandates/", {
    headers,
    data: {
      code_name: `Osprey ${reversed(RUN)}`,
      client_id: (await company.json()).id,
      type: "sell_side",
      sector_id: sectorId,
      lead_partner_id: partner.id,
      estimated_ev: "25000",
    },
  });
  expect(mandate.status(), await mandate.text()).toBe(201);
  const created = (await mandate.json()) as { id: number; code_name: string };
  const fees = await request.put(`/api/v1/mandates/${created.id}/fees`, {
    headers,
    data: { retainer_monthly: "10000", success_fee_kind: "percent", success_fee_percent: "2" },
  });
  expect(fees.status(), await fees.text()).toBe(200);
  const soon = new Date(Date.now() + 3 * 86_400_000).toISOString().slice(0, 10);
  const milestone = await request.post(`/api/v1/mandates/${created.id}/milestones`, {
    headers,
    data: { name: "Teaser out", planned_date: soon },
  });
  expect(milestone.status(), await milestone.text()).toBe(201);
  const today = new Date().toISOString().slice(0, 10);
  const task = await request.post("/api/v1/tasks/", {
    headers,
    data: { title: `Call the client ${RUN}`, assignee_id: partner.id, due_date: today },
  });
  expect(task.status(), await task.text()).toBe(201);
  await context.close();
  return created;
}

let deal: { id: number; code_name: string };

test.use({ storageState: { cookies: [], origins: [] } });

test.beforeAll(async ({ browser }) => {
  deal = await seed(browser);
});

async function signInAs(page: Page, identity: { email: string; password: string }) {
  await page.goto(LOGIN_PATH);
  await signIn(page, identity);
  await expect(page).not.toHaveURL(new RegExp(LOGIN_PATH));
}

// REP-01 c1: my active deals by stage, tasks due this week and upcoming key dates, under 2 seconds.
test("the home page shows my deals by stage, this week's tasks and key dates", async ({ page }) => {
  await signInAs(page, PARTNER);
  const started = Date.now();
  await page.goto("/overview");
  await expect(page.getByRole("link", { name: deal.code_name }).first()).toBeVisible();
  expect(Date.now() - started).toBeLessThan(2000);
  const stage = page.getByRole("region").filter({ has: page.getByRole("link", { name: deal.code_name }) });
  await expect(stage).toHaveCount(1);
  await expect(stage.getByRole("heading")).toContainText(/Conflict review|Preparation/);
  await expect(page.getByText(`Call the client ${RUN}`)).toBeVisible();
  await expect(page.getByText(`${deal.code_name}: Teaser out`)).toBeVisible();
});

// REP-01 c2: a new user gets guidance on how to start.
test("a new user's home page shows how to start", async ({ page }) => {
  await signInAs(page, NEWCOMER);
  await page.goto("/overview");
  await expect(page.getByRole("heading", { name: "Welcome. Here is how to start" })).toBeVisible();
});

// REP-02 c1: the partner sets a close forecast and sees the weighted fee by quarter on the dashboard.
test("the firm dashboard counts mandates and weights expected fees by quarter", async ({ page }) => {
  await signInAs(page, PARTNER);
  await page.goto(`/deals/${deal.id}`);
  await page.getByLabel("Probability (%)").fill("50");
  await page.getByLabel("Expected closing date").fill("2027-02-15");
  const saved = page.waitForResponse((response) => response.url().endsWith(`/mandates/${deal.id}/forecast`) && response.request().method() === "PUT");
  await page.getByRole("button", { name: "Update forecast" }).click();
  expect((await saved).status()).toBe(200);
  await expect(page.getByLabel("Probability (%)")).toHaveValue("50");

  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "Firm pipeline" })).toBeVisible();
  await expect(page.getByText(/Running mandates: \d+/)).toBeVisible();
  // The API figure is what the page must show; it includes this deal's 500000 x 50%.
  const api = (await (await page.request.get("/api/v1/reports/dashboard")).json()) as {
    weighted_fees_by_quarter: { quarter: string; weighted_fees: string }[];
  };
  const q1 = api.weighted_fees_by_quarter.find((row) => row.quarter === "2027-Q1")!;
  expect(Number(q1.weighted_fees)).toBeGreaterThanOrEqual(250000);
  await expect(page.getByRole("row").filter({ hasText: "2027-Q1" })).toContainText(q1.weighted_fees);
  await expect(page.getByText(deal.code_name)).toHaveCount(0);
});

// REP-03: back-office sees 12 months of forecast vs actual and downloads the Excel file.
test("back-office sees the 12-month fee forecast and exports it to Excel", async ({ page }) => {
  await signInAs(page, BACK_OFFICE);
  await page.goto("/fee-forecast");
  await expect(page.getByRole("heading", { name: "Fee forecast, next 12 months" })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(12);
  await expect(page.getByRole("columnheader", { name: "Invoiced (EUR)" })).toBeVisible();
  // AUTH-02 c5: a mass export asks the code again.
  await page.getByRole("button", { name: "Export to Excel" }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByLabel("Authentication code").fill("000000");
  await dialog.getByRole("button", { name: "Export" }).click();
  await expect(dialog.getByText("That code is not valid.", { exact: false })).toBeVisible();
  const download = page.waitForEvent("download");
  await dialog.getByLabel("Authentication code").fill(currentCode(BACK_OFFICE.email));
  await dialog.getByRole("button", { name: "Export" }).click();
  expect((await download).suggestedFilename()).toBe("fee-forecast.xlsx");
});

// REP-04: the partner runs the win/loss report for a period.
test("a partner runs the win/loss report for a period", async ({ page }) => {
  await signInAs(page, PARTNER);
  await page.goto("/win-loss");
  await page.getByLabel("From").fill("2020-01-01");
  await page.getByLabel("To").fill("2030-12-31");
  await page.getByRole("button", { name: "Run report" }).click();
  await expect(page.getByText("Pitches", { exact: true })).toBeVisible();
  await expect(page.getByText("Win rate", { exact: true })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Average EV/EBITDA" })).toBeVisible();
});

// ROLE-01 c3 + AUTHZ-02 c4: Read-only gets the aggregated dashboard and nothing else.
test("read-only sees the aggregated dashboard and no record", async ({ page }) => {
  await signInAs(page, READER);
  await page.goto("/overview");
  await expect(page.getByText("Your role sees the aggregated dashboards.")).toBeVisible();
  const nav = page.getByRole("navigation").first();
  await expect(nav.getByRole("link", { name: "Deals" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Companies" })).toHaveCount(0);

  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "Firm pipeline" })).toBeVisible();
  await expect(page.getByText(deal.code_name)).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Weighted expected fees by quarter" })).toHaveCount(0);

  for (const path of ["/api/v1/mandates/", `/api/v1/mandates/${deal.id}`, "/api/v1/companies/", "/api/v1/contacts/"]) {
    const response = await page.request.get(path);
    expect([403, 404], path).toContain(response.status());
  }
});
