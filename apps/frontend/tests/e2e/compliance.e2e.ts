import { expect, test, type Browser } from "@playwright/test";
import { LOGIN_PATH } from "@/lib/auth-routing";
import { ADMIN, inviteUser, signIn, signInApi, runId } from "./identities";

const PARTNER = {
  firstName: "Pieter",
  lastName: "Partner",
  email: "e2e.partner@example.com",
  password: "Copper-Meadow-42-Signal",
};
const COMPLIANCE = {
  firstName: "Clara",
  lastName: "Compliance",
  email: "e2e.compliance@example.com",
  password: "Granite-Harbour-17-Beacon",
};
const RUN = runId();
const reversed = (text: string) => text.split("").reverse().join("");

/**
 * An existing deal selling Northwind with "Brasserie … NV" as target, then a new mandate for
 * "Brasserie … SA" as client: same company on the other side, differing only by legal form.
 */
async function seedConflict(browser: Browser) {
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const adminHeaders = await signInApi(admin, ADMIN);
  await inviteUser(browser, admin, adminHeaders, PARTNER, "Partner");
  await inviteUser(browser, admin, adminHeaders, COMPLIANCE, "Compliance / Back-office");
  const sector = await admin.post("/api/v1/picklists/", {
    headers: adminHeaders,
    data: { kind: "sector", code: `cmp-${RUN}`, label_en: `Compliance sector ${RUN}` },
  });
  expect(sector.status(), await sector.text()).toBe(201);
  const sectorId = (await sector.json()).id as number;
  await adminContext.close();

  const context = await browser.newContext();
  const request = context.request;
  const headers = await signInApi(request, PARTNER);
  const partner: { id: number } = await (await request.get("/api/v1/users/me")).json();
  const countries: { id: number; code: string }[] = await (await request.get("/api/v1/picklists/?kind=country")).json();
  const company = async (name: string) => {
    const response = await request.post("/api/v1/companies/", {
      headers,
      data: {
        name,
        type: "target",
        country_id: countries.find((country) => country.code === "NL")!.id,
        vat_or_registry_number: `${name}-${RUN}`,
        ignore_similar: true,
      },
    });
    expect(response.status(), await response.text()).toBe(201);
    return (await response.json()).id as number;
  };
  const tag = RUN.toUpperCase();
  const seller = await company(`Northwind ${tag}`);
  const existing = await company(`Brasserie Qx${tag} NV`);
  const sameButSa = await company(`Brasserie Qx${tag} SA`);
  const create = async (codeName: string, clientId: number, targetId?: number) => {
    const response = await request.post("/api/v1/mandates/", {
      headers,
      data: {
        code_name: codeName,
        client_id: clientId,
        target_id: targetId,
        type: "sell_side",
        sector_id: sectorId,
        lead_partner_id: partner.id,
        estimated_ev: "5000",
      },
    });
    expect(response.status(), await response.text()).toBe(201);
    return (await response.json()) as { id: number; code_name: string; conflict_status: string };
  };
  const heron = await create(`Heron ${reversed(RUN)}`, seller, existing);
  const falcon = await create(`Falcon ${reversed(RUN)}`, sameButSa);
  expect(falcon.conflict_status).toBe("review");
  await context.close();
  return { heron, falcon };
}

let deals: Awaited<ReturnType<typeof seedConflict>>;

test.use({ storageState: { cookies: [], origins: [] } });

test.beforeAll(async ({ browser }) => {
  deals = await seedConflict(browser);
});

// AUTHZ-05 c2/c3/c4 + ORI-05 c2/c4 in the browser.
test("compliance reviews the conflict and KYC; the creator sees the status but not the other deal", async ({ browser }) => {
  const creator = await browser.newPage();
  await creator.goto(LOGIN_PATH);
  await signIn(creator, PARTNER);
  await creator.goto(`/deals/${deals.falcon.id}`);
  await creator.getByRole("tab", { name: "Compliance" }).click();
  await expect(creator.locator('[data-conflict="review"]')).toHaveText("In conflict review");
  await expect(creator.getByText("Only compliance can see what it conflicts with.")).toBeVisible();
  await expect(creator.getByText(deals.heron.code_name)).toHaveCount(0);

  const page = await browser.newPage();
  await page.goto(LOGIN_PATH);
  await signIn(page, COMPLIANCE);
  await page.goto("/conflict-reviews");
  await page.locator(`[data-review="${deals.falcon.code_name}"]`).getByRole("link").click();
  await expect(page).toHaveURL(new RegExp(`/deals/${deals.falcon.id}$`));
  await page.getByRole("tab", { name: "Compliance" }).click();
  const hits = page.getByRole("table", { name: "Potential conflicts" });
  await expect(hits).toContainText(`Brasserie Qx${RUN.toUpperCase()} SA`);
  await expect(hits).toContainText(`Brasserie Qx${RUN.toUpperCase()} NV`);
  await expect(hits).toContainText(deals.heron.code_name);

  await page.getByLabel("UBO check done").click();
  await page.getByLabel("ID check done").click();
  await page.getByLabel("PEP / sanctions screening done").click();
  await expect(page.getByText("KYC status: Approved")).toBeVisible();
  await page.getByRole("button", { name: "Save KYC review" }).click();
  await expect(page.getByText(/Approved on .* by /)).toBeVisible();

  await page.getByLabel("Sanctions hit").click();
  await page.getByRole("button", { name: "Save KYC review" }).click();
  await expect(page.getByText("frozen after a sanctions hit", { exact: false })).toBeVisible();
  await creator.reload();
  await creator.getByRole("tab", { name: "Compliance" }).click();
  await expect(creator.getByText("frozen after a sanctions hit", { exact: false })).toBeVisible();
  await expect(creator.getByRole("button", { name: "Unfreeze" })).toHaveCount(0);

  await page.getByLabel("Reason to unfreeze").fill("False positive, name match only");
  await page.getByRole("button", { name: "Unfreeze" }).click();
  await expect(page.getByText("frozen after a sanctions hit", { exact: false })).toHaveCount(0);

  await expect(page.getByRole("button", { name: "Clear" })).toBeDisabled();
  await page.getByLabel("Reason", { exact: true }).fill("Different teams, no overlap");
  await expect(page.getByLabel("Reason", { exact: true })).toHaveValue("Different teams, no overlap");
  await expect(page.getByRole("button", { name: "Clear" })).toBeEnabled();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.locator('[data-conflict="cleared"]')).toHaveText("Cleared by compliance");
  await creator.reload();
  await creator.getByRole("tab", { name: "Compliance" }).click();
  await expect(creator.locator('[data-conflict="cleared"]')).toHaveText("Cleared by compliance");
});
