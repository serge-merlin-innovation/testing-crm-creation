import { expect, test, type Browser } from "@playwright/test";
import { LOGIN_PATH } from "@/lib/auth-routing";
import { ADMIN, inviteUser, signIn, signInApi, runId } from "./identities";

const PARTNER = {
  firstName: "Pieter",
  lastName: "Partner",
  email: "e2e.partner@example.com",
  password: "Copper-Meadow-42-Signal",
  name: "Pieter Partner",
};
const RUN = runId();
const reversed = (text: string) => text.split("").reverse().join("");

/** Two partner-owned deals on the board, created through the API. */
async function seedDeals(browser: Browser) {
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const adminHeaders = await signInApi(admin, ADMIN);
  await inviteUser(browser, admin, adminHeaders, PARTNER, "Partner");
  const sector = await admin.post("/api/v1/picklists/", {
    headers: adminHeaders,
    data: { kind: "sector", code: `pipe-${RUN}`, label_en: `Pipeline sector ${RUN}` },
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
      name: `Zephyrine Tools ${RUN.toUpperCase()}x`,
      type: "target",
      country_id: countries.find((country) => country.code === "NL")!.id,
      vat_or_registry_number: `NLP-${RUN}`,
      ignore_similar: true,
    },
  });
  expect(company.status(), await company.text()).toBe(201);
  const create = async (codeName: string, ev: string) => {
    const response = await request.post("/api/v1/mandates/", {
      headers,
      data: {
        code_name: codeName,
        client_id: (await company.json()).id,
        type: "sell_side",
        sector_id: sectorId,
        lead_partner_id: partner.id,
        estimated_ev: ev,
      },
    });
    expect(response.status(), await response.text()).toBe(201);
    return (await response.json()) as { id: number; code_name: string };
  };
  const kestrel = await create(`Kestrel ${reversed(RUN)}`, "5000");
  const plover = await create(`Plover ${reversed(RUN)}`, "90000");
  await context.close();
  return { kestrel, plover };
}

let deals: Awaited<ReturnType<typeof seedDeals>>;

test.use({ storageState: { cookies: [], origins: [] } });

test.beforeAll(async ({ browser }) => {
  deals = await seedDeals(browser);
});

test.beforeEach(async ({ page }) => {
  await page.goto(LOGIN_PATH);
  await signIn(page, PARTNER);
  await expect(page).not.toHaveURL(new RegExp(LOGIN_PATH));
});

/** DEAL-02 c3 in the browser: the sector filter narrows the board to this run's deals. */
async function openBoard(page: import("@playwright/test").Page) {
  await page.goto("/deals");
  await page.getByLabel("Sector").first().click();
  await page.getByRole("option", { name: `Pipeline sector ${RUN}` }).click();
  await expect(page.locator("[data-deal]")).toHaveCount(2);
}

const column = (page: import("@playwright/test").Page, stage: string) => page.locator(`section[data-stage="${stage}"]`);
const card = (page: import("@playwright/test").Page, codeName: string) => page.locator(`[data-deal="${codeName}"]`);

// DEAL-02 c1, c2, c4: drag saves stage and history; an unmet exit criterion blocks with its reason;
// dragging back asks for a reason.
test("dragging a deal on the board moves it, is blocked by exit criteria, and asks why when going back", async ({
  page,
}) => {
  const name = deals.kestrel.code_name;
  await openBoard(page);
  await expect(card(page, name)).toBeVisible();
  await expect(column(page, "conflict_review").locator(`[data-deal="${name}"]`)).toBeVisible();

  await card(page, name).dragTo(column(page, "preparation"));
  await expect(column(page, "preparation").locator(`[data-deal="${name}"]`)).toBeVisible();

  await card(page, name).dragTo(column(page, "marketing"));
  await expect(page.getByText(`Cannot move ${name}`)).toBeVisible();
  await expect(page.getByText("KYC must be approved.")).toBeVisible();
  await expect(column(page, "preparation").locator(`[data-deal="${name}"]`)).toBeVisible();

  await card(page, name).dragTo(column(page, "conflict_review"));
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Move" })).toBeDisabled();
  await dialog.getByLabel("Reason").fill("Conflict check reopened");
  await dialog.getByRole("button", { name: "Move" }).click();
  await expect(column(page, "conflict_review").locator(`[data-deal="${name}"]`)).toBeVisible();

  await page.goto(`/deals/${deals.kestrel.id}`);
  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.getByRole("row").filter({ hasText: "stage_reason" }).first()).toContainText("Conflict check reopened");
  await expect(page.getByRole("row").filter({ hasText: "preparation" }).first()).toBeVisible();
});

// DEAL-02 c5: the list toggle shows the same deals as a sortable table.
test("the list view shows the same deals, sortable", async ({ page }) => {
  await openBoard(page);
  await page.getByRole("tab", { name: "List" }).click();

  const rows = page.getByRole("row").filter({ hasText: reversed(RUN) });
  await expect(rows).toHaveCount(2);
  await page.getByRole("button", { name: /Estimated EV/ }).click();
  await expect(rows.first()).toContainText(deals.kestrel.code_name);
  await page.getByRole("button", { name: /Estimated EV/ }).click();
  await expect(rows.first()).toContainText(deals.plover.code_name);
});

// DEAL-04 c1: a milestone whose actual date is later than planned shows red with the days late.
test("a late milestone is shown in red with the days late", async ({ page }) => {
  await page.goto(`/deals/${deals.plover.id}`);
  await page.getByRole("tab", { name: "Milestones" }).click();
  await page.getByRole("textbox", { name: "Milestone" }).fill("IM sent");
  await page.getByLabel("Planned date").fill("2026-01-05");
  await page.getByRole("button", { name: "Add milestone" }).click();

  const row = page.getByRole("row").filter({ hasText: "IM sent" });
  await row.getByLabel("Actual date IM sent").fill("2026-01-09");
  await row.getByLabel("Actual date IM sent").blur();
  const badge = row.getByText("4 days late");
  await expect(badge).toBeVisible();
  await expect(badge).toHaveAttribute("data-variant", "destructive");
});

// DEAL-06 c2 + c3: aborting needs a reason and locks the deal; reopening needs a reason.
test("aborting needs a reason and makes the deal read-only until reopened", async ({ page }) => {
  await page.goto(`/deals/${deals.plover.id}`);
  await page.getByRole("tab", { name: "Closing" }).click();
  await page.getByLabel("Outcome").click();
  await page.getByRole("option", { name: "Aborted" }).click();
  await page.getByRole("button", { name: "Close the deal" }).click();
  await expect(page.getByText("Say why the deal was aborted")).toBeVisible();

  await page.getByLabel("Abort reason").fill("Seller withdrew");
  await page.getByRole("button", { name: "Close the deal" }).click();
  await expect(page.getByText("This deal is closed and read-only.")).toBeVisible();
  await page.getByRole("tab", { name: "Summary" }).click();
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);

  await page.getByRole("tab", { name: "Closing" }).click();
  await page.getByLabel("Reason to reopen").fill("Seller is back");
  await page.getByRole("button", { name: "Reopen the deal" }).click();
  await expect(page.getByRole("button", { name: "Close the deal" })).toBeVisible();
});
