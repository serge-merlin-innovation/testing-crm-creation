import { expect, test, type Browser, type Page } from "@playwright/test";
import { LOGIN_PATH } from "@/lib/auth-routing";
import { ADMIN, MEMBER, inviteUser, signIn, signInApi, runId } from "./identities";

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
const RUN = runId();
const reversed = (text: string) => text.split("").reverse().join("");

/** A partner-led deal at EV 25m with the banked analyst on the team. Back-office is not staffed. */
async function seedDeal(browser: Browser) {
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const adminHeaders = await signInApi(admin, ADMIN);
  await inviteUser(browser, admin, adminHeaders, PARTNER, "Partner");
  await inviteUser(browser, admin, adminHeaders, BACK_OFFICE, "Compliance / Back-office");
  const sector = await admin.post("/api/v1/picklists/", {
    headers: adminHeaders,
    data: { kind: "sector", code: `fee-${RUN}`, label_en: `Fee sector ${RUN}` },
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
      name: `Valemont Optics ${RUN.toUpperCase()}x`,
      type: "target",
      country_id: countries.find((country) => country.code === "NL")!.id,
      vat_or_registry_number: `NLF-${RUN}`,
      ignore_similar: true,
    },
  });
  expect(company.status(), await company.text()).toBe(201);
  const mandate = await request.post("/api/v1/mandates/", {
    headers,
    data: {
      code_name: `Merlin ${reversed(RUN)}`,
      client_id: (await company.json()).id,
      type: "sell_side",
      sector_id: sectorId,
      lead_partner_id: partner.id,
      estimated_ev: "25000",
    },
  });
  expect(mandate.status(), await mandate.text()).toBe(201);
  const created = (await mandate.json()) as { id: number; code_name: string };
  const candidates: { id: number; email: string }[] = await (
    await request.get(`/api/v1/mandates/${created.id}/team/candidates`)
  ).json();
  const member = candidates.find((user) => user.email === MEMBER.email);
  expect(member, "banked analyst").toBeTruthy();
  const staffed = await request.post(`/api/v1/mandates/${created.id}/team`, {
    headers,
    data: { user_id: member!.id, role: "analyst" },
  });
  expect(staffed.status(), await staffed.text()).toBe(201);
  await context.close();
  return created;
}

let deal: { id: number; code_name: string };

test.use({ storageState: { cookies: [], origins: [] } });

test.beforeAll(async ({ browser }) => {
  deal = await seedDeal(browser);
});

async function signInAs(page: Page, identity: { email: string; password: string }) {
  await page.goto(LOGIN_PATH);
  await signIn(page, identity);
  await expect(page).not.toHaveURL(new RegExp(LOGIN_PATH));
}

async function openFees(page: Page) {
  await page.goto(`/deals/${deal.id}`);
  await page.getByRole("tab", { name: "Fees" }).click();
}

const row = (page: Page, label: string) => page.getByRole("row").filter({ hasText: label });

// DEAL-05 c1 + c3, ROLE-01 c5: the lead partner records the fee terms and sees the expected fee from the
// estimated EV; after the engagement letter is linked a change asks for a reason and the amended letter.
test("a partner records fee terms, sees the expected fee, and must justify a change after engagement", async ({
  page,
}) => {
  await signInAs(page, PARTNER);
  await openFees(page);

  await page.getByLabel("Retainer (EUR / month)").fill("10000");
  await page.getByLabel("Success fee (% of EV)").fill("2");
  await page.getByRole("button", { name: "Save fees" }).click();
  await expect(row(page, "Expected fee (EUR)")).toContainText("500,000");

  await page.getByRole("tab", { name: "Documents" }).click();
  await page.getByLabel("Label (e.g. IM, Financials, VDR)").fill("Engagement letter");
  await page.getByLabel("https link").fill("https://files.example.com/el.pdf");
  await page.getByRole("button", { name: "Add link" }).click();
  await expect(page.getByRole("link", { name: "https://files.example.com/el.pdf" })).toBeVisible();

  await page.getByRole("tab", { name: "Fees" }).click();
  await page.getByLabel("Success fee (% of EV)").fill("3");
  await expect(page.getByText("The engagement letter is signed")).toBeVisible();
  await page.getByRole("button", { name: "Save fees" }).click();
  await expect(page.getByText("Say why the fees changed after engagement")).toBeVisible();
  await page.getByLabel("Reason for the change").fill("Client renegotiated");
  await page.getByLabel("Amended engagement letter (link)").fill("https://files.example.com/el-v2.pdf");
  await page.getByRole("button", { name: "Save fees" }).click();
  await expect(row(page, "Expected fee (EUR)")).toContainText("750,000");
});

// AUTHZ-06 c1 + c3: the staffed analyst sees the deal but no fee tab, no Fees page and no fee filter.
test("an analyst on the deal sees no fee fields, fee page or fee filter", async ({ page }) => {
  await signInAs(page, MEMBER);
  await page.goto(`/deals/${deal.id}`);
  await expect(page.getByRole("heading", { name: deal.code_name })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Fees" })).toHaveCount(0);
  await expect(page.getByText("Expected fee")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Fees" })).toHaveCount(0);

  await page.goto("/fees");
  await expect(page.getByLabel("Expected fee at least (EUR)")).toHaveCount(0);
  const api = await page.request.get(`/api/v1/mandates/${deal.id}/fees`);
  expect(api.status()).toBe(403);
});

// ROLE-01 c4 + REP-07 c1 + AUTHZ-06 c2: back-office, not staffed, reads the summary and fees, records an
// invoice, and finds the fee filter on the Fees page; the deal notes stay hidden.
test("back-office reads the summary and fees of an unstaffed deal and records an invoice", async ({ page }) => {
  await signInAs(page, BACK_OFFICE);
  await page.goto(`/deals/${deal.id}`);
  await expect(page.getByRole("heading", { name: deal.code_name })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Team" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "History" })).toHaveCount(0);

  await page.getByRole("tab", { name: "Fees" }).click();
  await expect(row(page, "Expected fee (EUR)")).toContainText("750,000");
  await page.getByLabel("Amount (EUR)").fill("10000");
  await page.getByLabel("Sent on").fill("2026-10-01");
  await page.getByRole("button", { name: "Record invoice" }).click();
  await expect(page.locator("[data-invoice]")).toHaveCount(1);
  await expect(page.locator("[data-invoice]")).toContainText("10,000.00");

  const timeline = await page.request.get(`/api/v1/timeline/mandate/${deal.id}`);
  expect(timeline.status()).toBe(404);

  await page.goto("/fees");
  await page.getByLabel("Expected fee at least (EUR)").fill("700000");
  await expect(page.locator(`[data-fee-row="${deal.code_name}"]`)).toBeVisible();
  await page.getByLabel("Expected fee at least (EUR)").fill("900000000");
  await expect(page.locator(`[data-fee-row="${deal.code_name}"]`)).toHaveCount(0);
});
