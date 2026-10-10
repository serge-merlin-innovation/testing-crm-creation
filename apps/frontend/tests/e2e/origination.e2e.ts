import { expect, test, type Browser, type Page } from "@playwright/test";
import { LOGIN_PATH } from "@/lib/auth-routing";
import { ADMIN, MEMBER, inviteUser, signIn, signInApi } from "./identities";

const PARTNER = {
  firstName: "Pieter",
  lastName: "Partner",
  email: "e2e.partner@example.com",
  password: "Copper-Meadow-42-Signal",
};
const RUN = Date.now().toString(36);
const reversed = (text: string) => text.split("").reverse().join("");
const COMPANY = `Brightwater Foods ${RUN.toUpperCase()}x`;
const TOMBSTONE = `Tern ${reversed(RUN)}`;
const PRIVATE_DEAL = `Shrike ${reversed(RUN)}`;

type Seed = { sectorLabel: string; companyId: number };

/** A sector, a prospect company, and two closed deals in that sector: one with a tombstone allowed. */
async function seed(browser: Browser): Promise<Seed> {
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const adminHeaders = await signInApi(admin, ADMIN);
  await inviteUser(browser, admin, adminHeaders, PARTNER, "Partner");
  const sectorLabel = `Origination sector ${RUN}`;
  const sector = await admin.post("/api/v1/picklists/", {
    headers: adminHeaders,
    data: { kind: "sector", code: `ori-${RUN}`, label_en: sectorLabel },
  });
  expect(sector.status(), await sector.text()).toBe(201);
  const sectorId = (await sector.json()).id as number;
  await adminContext.close();

  const context = await browser.newContext();
  const request = context.request;
  const headers = await signInApi(request, PARTNER);
  const partner: { id: number } = await (await request.get("/api/v1/users/me")).json();
  const countries: { id: number; code: string }[] = await (await request.get("/api/v1/picklists/?kind=country")).json();
  const countryId = countries.find((country) => country.code === "NL")!.id;

  async function company(name: string) {
    const response = await request.post("/api/v1/companies/", {
      headers,
      data: { name, type: "target", country_id: countryId, vat_or_registry_number: `NLO-${name}`, ignore_similar: true },
    });
    expect(response.status(), await response.text()).toBe(201);
    return (await response.json()).id as number;
  }

  async function closedDeal(codeName: string, sellerName: string, tombstone: boolean) {
    const created = await request.post("/api/v1/mandates/", {
      headers,
      data: {
        code_name: codeName,
        client_id: await company(sellerName),
        type: "sell_side",
        sector_id: sectorId,
        lead_partner_id: partner.id,
        estimated_ev: "30000",
      },
    });
    expect(created.status(), await created.text()).toBe(201);
    const mandate = (await created.json()) as { id: number; version: number };
    const closed = await request.post(`/api/v1/mandates/${mandate.id}/close`, {
      headers,
      data: {
        version: mandate.version,
        outcome: "closed_won",
        final_ev: "30000",
        buyer: "A buyer",
        ev_ebitda: "7",
        closing_date: "2026-03-01",
        tombstone_allowed: tombstone,
      },
    });
    expect(closed.status(), await closed.text()).toBe(200);
  }

  await closedDeal(TOMBSTONE, `Harbour Mills ${RUN}`, true);
  await closedDeal(PRIVATE_DEAL, `Quayside Tools ${RUN}`, false);
  const companyId = await company(COMPANY);
  await context.close();
  return { sectorLabel, companyId };
}

let seeded: Seed;

test.use({ storageState: { cookies: [], origins: [] } });

test.beforeAll(async ({ browser }) => {
  seeded = await seed(browser);
});

async function signInAs(page: Page, identity: { email: string; password: string }) {
  await page.goto(LOGIN_PATH);
  await signIn(page, identity);
  await expect(page).not.toHaveURL(new RegExp(LOGIN_PATH));
}

async function choose(page: Page, label: string, option: string) {
  await page.getByLabel(label, { exact: true }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

let opportunityPath = "";

// ORI-01 c1-c3, ORI-02 c1-c2, ORI-03 c1: the partner logs an opportunity, attaches a pitch deck and a
// public credential, invites the analyst, then confirms Won and lands on the new mandate.
test("a partner logs an opportunity, attaches pitch materials and credentials, and wins it", async ({ page }) => {
  await signInAs(page, PARTNER);
  await page.goto("/origination");
  await expect(page.getByRole("heading", { name: "Origination pipeline" })).toBeVisible();
  for (const stage of ["Lead", "Contacted", "Meeting held", "Pitch", "Engagement letter sent", "Won", "Lost", "On hold"]) {
    await expect(page.getByRole("region", { name: stage, exact: true })).toBeVisible();
  }

  await choose(page, "Company", COMPANY);
  await choose(page, "Trigger", "Succession");
  await choose(page, "Sector", seeded.sectorLabel);
  await page.getByLabel("Estimated EV (EUR thousands)").fill("45000");
  await page.getByLabel("Probability (%)").fill("40");
  await page.getByRole("button", { name: "Create opportunity" }).click();
  await expect(page.getByRole("heading", { name: COMPANY })).toBeVisible();
  opportunityPath = new URL(page.url()).pathname;

  await page.getByLabel("Document link (https)").fill("https://files.example.com/pitch.pptx");
  await page.getByRole("button", { name: "Add link" }).click();
  await expect(page.getByRole("link", { name: "https://files.example.com/pitch.pptx" })).toBeVisible();

  await choose(page, "Sector", seeded.sectorLabel);
  await page.getByLabel("EV from (EUR thousands)").fill("10000");
  await page.getByLabel("EV to (EUR thousands)").fill("50000");
  await page.getByRole("button", { name: "Search credentials" }).click();
  await expect(page.locator(`[data-credential-result="${TOMBSTONE}"]`)).toBeVisible();
  await expect(page.locator(`[data-credential-result="${PRIVATE_DEAL}"]`)).toHaveCount(0);
  await page.locator(`[data-credential-result="${TOMBSTONE}"]`).getByRole("button", { name: "Add as credential" }).click();
  await expect(page.locator(`[data-credential="${TOMBSTONE}"]`)).toBeVisible();

  await choose(page, "Colleague", `${MEMBER.firstName} ${MEMBER.lastName}`);
  await page.getByRole("button", { name: "Invite" }).click();
  await expect(page.getByRole("list", { name: "Invited colleagues" })).toContainText(MEMBER.firstName);

  await page.getByLabel("Retainer (EUR / month)").fill("12000");
  await page.getByLabel("Success fee (% of EV)").fill("2");
  await page.getByRole("button", { name: "Save fee draft" }).click();
  await expect(page.getByText("Fee draft saved.")).toBeVisible();

  await page.getByLabel("Code name of the new mandate").fill(`Plume ${reversed(RUN)}`);
  await page.getByRole("button", { name: "Confirm Won" }).click();
  await page.getByRole("link", { name: "Open the mandate" }).click();
  await expect(page.getByRole("heading", { name: `Plume ${reversed(RUN)}` })).toBeVisible();
});

// ORI-01 c3: the invited analyst reads the opportunity; the admin (no deal role) gets Not found, page and API.
test("only the owner and invited colleagues see the opportunity", async ({ page, browser }) => {
  await signInAs(page, MEMBER);
  await page.goto(opportunityPath);
  await expect(page.getByRole("heading", { name: COMPANY })).toBeVisible();

  const adminContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  await signInAs(adminPage, ADMIN);
  await adminPage.goto(opportunityPath);
  await expect(adminPage.getByRole("heading", { name: COMPANY })).toHaveCount(0);
  const id = opportunityPath.split("/").pop();
  expect((await adminPage.request.get(`/api/v1/origination/opportunities/${id}`)).status()).toBe(404);
  await adminContext.close();
});

// ORI-01 c4 + ORI-03 c2: the company now has an active mandate, so a new opportunity warns; losing it
// asks for a reason, and the competitor is optional.
test("a company on an active mandate warns, and Lost needs a reason", async ({ page }) => {
  await signInAs(page, PARTNER);
  await page.goto("/origination");
  await choose(page, "Company", COMPANY);
  await expect(page.getByText("This company is on an active mandate")).toBeVisible();
  await page.getByLabel("Estimated EV (EUR thousands)").fill("20000");
  await page.getByLabel("Probability (%)").fill("10");
  await page.getByRole("button", { name: "Create opportunity" }).click();
  await expect(page.getByRole("heading", { name: COMPANY })).toBeVisible();
  await expect(page.getByText("This company is on an active mandate")).toBeVisible();

  await choose(page, "Stage", "Lost");
  await page.getByRole("button", { name: "Move" }).click();
  await expect(page.getByText("Say why the opportunity was lost")).toBeVisible();
  await choose(page, "Lost reason", "Competitor");
  await page.getByLabel("Competitor advisor (optional)").fill("Rival Corporate Finance");
  await page.getByRole("button", { name: "Move" }).click();
  await expect(page.getByRole("row", { name: /Lost reason/ })).toContainText("Competitor");
  await expect(page.getByRole("row", { name: /Competitor advisor/ })).toContainText("Rival Corporate Finance");
});

// ORI-03 c3: On hold asks for the revisit date; when the date comes (test clock + job), the owner has a task.
test("on hold creates an owner task on the revisit date", async ({ page }) => {
  await signInAs(page, PARTNER);
  await page.goto("/origination");
  await choose(page, "Company", COMPANY);
  await page.getByLabel("Estimated EV (EUR thousands)").fill("15000");
  await page.getByLabel("Probability (%)").fill("20");
  await page.getByRole("button", { name: "Create opportunity" }).click();
  await expect(page.getByRole("heading", { name: COMPANY })).toBeVisible();

  await choose(page, "Stage", "On hold");
  await page.getByLabel("Revisit on").fill("2031-01-06");
  await page.getByRole("button", { name: "Move" }).click();
  await expect(page.getByRole("row", { name: /Revisit on/ })).toContainText("06/01/2031");

  const clock = await page.request.put("/api/v1/test-hooks/clock", { data: { now: "2031-01-06T08:00:00Z" } });
  expect(clock.status(), await clock.text()).toBeLessThan(300);
  try {
    const run = await page.request.post("/api/v1/test-hooks/jobs/run");
    expect(run.status(), await run.text()).toBeLessThan(300);
  } finally {
    await page.request.put("/api/v1/test-hooks/clock", { data: { now: null } });
  }
  const tasks: { title: string; due_date: string }[] = await (await page.request.get("/api/v1/tasks/mine")).json();
  expect(tasks.some((task) => task.title === `Revisit the opportunity on ${COMPANY}` && task.due_date === "2031-01-06")).toBe(
    true,
  );
});
