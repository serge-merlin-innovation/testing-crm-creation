import { expect, test, type Browser } from "@playwright/test";
import { LOGIN_PATH } from "@/lib/auth-routing";
import { ADMIN, inviteUser, signIn, signInApi } from "./identities";

const PARTNER = {
  firstName: "Pieter",
  lastName: "Partner",
  email: "e2e.partner@example.com",
  password: "Copper-Meadow-42-Signal",
};
const RUN = Date.now().toString(36);
const TAG = RUN.toUpperCase();

/** A deal with a staffed partner, a buyer with an investor profile that matches, and one that matches nothing. */
async function seedDeal(browser: Browser) {
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const adminHeaders = await signInApi(admin, ADMIN);
  await inviteUser(browser, admin, adminHeaders, PARTNER, "Partner");
  const sector = await admin.post("/api/v1/picklists/", {
    headers: adminHeaders,
    data: { kind: "sector", code: `buy-${RUN}`, label_en: `Buyer sector ${RUN}` },
  });
  expect(sector.status(), await sector.text()).toBe(201);
  const sectorId = (await sector.json()).id as number;
  await adminContext.close();

  const context = await browser.newContext();
  const request = context.request;
  const headers = await signInApi(request, PARTNER);
  const partner: { id: number } = await (await request.get("/api/v1/users/me")).json();
  const countries: { id: number; code: string }[] = await (await request.get("/api/v1/picklists/?kind=country")).json();
  const nl = countries.find((country) => country.code === "NL")!.id;
  const company = async (name: string, type: string) => {
    const response = await request.post("/api/v1/companies/", {
      headers,
      data: { name, type, country_id: nl, vat_or_registry_number: `${name}-${RUN}`, ignore_similar: true },
    });
    expect(response.status(), await response.text()).toBe(201);
    return (await response.json()).id as number;
  };
  const client = await company(`Clientco ${TAG}`, "target");
  const fund = await company(`Bluewater ${TAG} Capital`, "financial_investor");
  const profile = await request.put(`/api/v1/companies/${fund}/investor-profile`, {
    headers,
    data: { sector_ids: [sectorId], country_ids: [nl], ticket_min: "1", ticket_max: "20", stake: "majority" },
  });
  expect(profile.status(), await profile.text()).toBe(200);
  const mandate = await request.post("/api/v1/mandates/", {
    headers,
    data: {
      code_name: `Osprey ${RUN.split("").reverse().join("")}`,
      client_id: client,
      type: "sell_side",
      sector_id: sectorId,
      lead_partner_id: partner.id,
      estimated_ev: "5000",
    },
  });
  expect(mandate.status(), await mandate.text()).toBe(201);
  const mandateId = (await mandate.json()).id as number;
  await context.close();
  return { mandateId, fundName: `Bluewater ${TAG} Capital` };
}

let seeded: Awaited<ReturnType<typeof seedDeal>>;

test.use({ storageState: { cookies: [], origins: [] } });

test.beforeAll(async ({ browser }) => {
  seeded = await seedDeal(browser);
});

// BUY-01 c1/c4, BUY-02 c1/c2, BUY-03 c1/c2, BUY-04 c1 in the browser.
test("suggest and add a buyer, approve it, move it through the grid, sign the NDA and export", async ({ browser }) => {
  const page = await browser.newPage();
  await page.goto(LOGIN_PATH);
  await signIn(page, PARTNER);
  await page.goto(`/deals/${seeded.mandateId}`);
  await page.getByRole("tab", { name: "Buyers" }).click();

  await page.getByRole("button", { name: "Suggest buyers" }).click();
  const suggestions = page.getByRole("table", { name: "Suggest buyers" });
  await expect(suggestions).toContainText(seeded.fundName);
  await expect(suggestions).toContainText("sector, geography, size");
  await suggestions.getByRole("checkbox", { name: `Select ${seeded.fundName}` }).click();

  await page.getByRole("button", { name: "Add selected" }).click();
  await expect(page.getByText("Give a rationale for every buyer")).toBeVisible();
  await page.locator("#buyer-owner").click();
  await page.getByRole("option", { name: /e2e\.partner|Pieter/ }).click();
  await page.getByLabel("Rationale").fill("Platform fit");
  await page.getByRole("button", { name: "Add selected" }).click();
  await expect(page.getByRole("status")).toHaveText("1 added, 0 already on the list.");

  const grid = page.getByRole("table", { name: "Buyers", exact: true });
  const row = grid.locator(`[data-buyer="${seeded.fundName}"]`);
  await expect(row).toContainText("Platform fit");
  await expect(page.locator('[data-funnel="long_list"]')).toHaveText("Long list: 1");

  await row.getByRole("checkbox").click();
  await page.locator("#buyer-status").click();
  await page.getByRole("option", { name: "Contacted" }).click();
  await expect(page.getByText("Only buyers the client approved can be contacted.")).toBeVisible();
  await page.getByRole("button", { name: "Apply to selected" }).click();
  await expect(page.locator("[data-grid-error]")).toContainText("Only buyers the client approved can be contacted");

  await row.getByRole("combobox").click();
  await page.getByRole("option", { name: "Approved" }).click();
  await expect(row.getByRole("combobox")).toHaveText("Approved");
  await page.getByRole("button", { name: "Apply to selected" }).click();
  await expect(row.locator("[data-status]")).toContainText("Contacted");
  await expect(page.locator('[data-funnel="contacted"]')).toHaveText("Contacted: 1");

  await row.getByRole("checkbox").click();
  await page.locator("#buyer-status").click();
  await page.getByRole("option", { name: "IM sent" }).click();
  await page.getByRole("button", { name: "Apply to selected" }).click();
  await expect(page.locator("[data-grid-error]")).toContainText("needs a signed NDA");

  await row.getByRole("button", { name: "NDA" }).click();
  await page.getByLabel("Sent", { exact: true }).fill("2026-10-01");
  await page.getByLabel("Document link").fill("https://docs.example.com/nda.pdf");
  await page.getByRole("button", { name: "Save NDA" }).click();
  await expect(row.locator("[data-status]")).toContainText("NDA sent");
  await page.getByLabel("Signed", { exact: true }).fill("2026-10-05");
  await page.getByRole("button", { name: "Save NDA" }).click();
  await expect(row.locator("[data-status]")).toContainText("NDA signed");
  await expect(row.getByRole("link", { name: "Document link" })).toHaveAttribute("href", "https://docs.example.com/nda.pdf");

  await page.getByRole("button", { name: "Apply to selected" }).click();
  await expect(row.locator("[data-status]")).toContainText("IM sent");

  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export to Excel" }).click();
  expect((await download).suggestedFilename()).toMatch(/-buyers\.xlsx$/);
});
