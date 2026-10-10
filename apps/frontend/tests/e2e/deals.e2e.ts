import { expect, test, type APIRequestContext, type Browser } from "@playwright/test";
import { LOGIN_PATH } from "@/lib/auth-routing";
import { ADMIN, MEMBER, submitCredentials } from "./identities";

const PARTNER = { email: "e2e.partner@example.com", password: "E2ePartner!1", name: "E2E Partner" };
const RUN = Date.now().toString(36);

async function signIn(request: APIRequestContext, email: string, password: string) {
  const response = await request.post("/api/v1/auth/login", { form: { email, password } });
  expect(response.status(), await response.text()).toBe(200);
  return { "X-CSRF-Token": (await response.json()).csrf_token as string };
}

/** A partner-owned deal, created through the API. The banked analyst is not on its team. */
async function seedDeal(browser: Browser) {
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const adminHeaders = await signIn(admin, ADMIN.email, ADMIN.password);

  await admin.post("/api/v1/users/", {
    headers: adminHeaders,
    data: { name: PARTNER.name, email: PARTNER.email, password: PARTNER.password },
  });
  const roles: { id: number; name: string }[] = await (await admin.get("/api/v1/roles/")).json();
  const users: { data: { id: number; email: string }[] } = await (
    await admin.get("/api/v1/users/", { params: { items_per_page: 100 } })
  ).json();
  const partner = users.data.find((user) => user.email === PARTNER.email)!;
  await admin.patch(`/api/v1/users/${partner.id}/role`, {
    headers: adminHeaders,
    data: { role_id: roles.find((role) => role.name === "Partner")!.id },
  });
  const sector = await admin.post("/api/v1/picklists/", {
    headers: adminHeaders,
    data: { kind: "sector", code: `e2e-${RUN}`, label_en: `E2E sector ${RUN}` },
  });
  expect(sector.status(), await sector.text()).toBe(201);
  const sectorId = (await sector.json()).id as number;
  await adminContext.close();

  const partnerContext = await browser.newContext();
  const request = partnerContext.request;
  const headers = await signIn(request, PARTNER.email, PARTNER.password);
  const countries: { id: number; code: string }[] = await (await request.get("/api/v1/picklists/?kind=country")).json();
  const company = await request.post("/api/v1/companies/", {
    headers,
    data: {
      name: `Quintessa Labs ${RUN.toUpperCase()}x`,
      type: "target",
      country_id: countries.find((country) => country.code === "NL")!.id,
      vat_or_registry_number: `NL-${RUN}`,
      ignore_similar: true,
    },
  });
  expect(company.status(), await company.text()).toBe(201);
  const mandate = await request.post("/api/v1/mandates/", {
    headers,
    data: {
      code_name: `Osprey ${Date.now().toString(36).split("").reverse().join("")}`,
      client_id: (await company.json()).id,
      type: "buy_side",
      sector_id: sectorId,
      lead_partner_id: partner.id,
      estimated_ev: "12000",
    },
  });
  expect(mandate.status(), await mandate.text()).toBe(201);
  const created = await mandate.json();
  await partnerContext.close();
  return { id: created.id as number, codeName: created.code_name as string };
}

let deal: { id: number; codeName: string };

test.beforeAll(async ({ browser }) => {
  deal = await seedDeal(browser);
});

// AUTH-01 c7 + AUTHZ-02 c1: a deep link to a deal I cannot access lands on Not found after login.
test("a deep link to an inaccessible deal lands on Not found after login", async ({ page }) => {
  await page.goto(`/deals/${deal.id}`);
  await expect(page).toHaveURL(`${LOGIN_PATH}?next=${encodeURIComponent(`/deals/${deal.id}`)}`);

  await submitCredentials(page, MEMBER);

  await expect(page).toHaveURL(`/deals/${deal.id}`);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
  await expect(page.getByText(deal.codeName)).toHaveCount(0);
  await expect(page.getByText("Quintessa")).toHaveCount(0);
});

test.describe("the deal team", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test.beforeEach(async ({ page }) => {
    await page.goto(LOGIN_PATH);
    await submitCredentials(page, PARTNER);
    await expect(page).not.toHaveURL(new RegExp(LOGIN_PATH));
  });

  // DEAL-07 c1 + c2: a labelled https link opens in a new tab.
  test("adds a labelled https link that opens in a new tab", async ({ page }) => {
    await page.goto(`/deals/${deal.id}`);
    await expect(page.getByRole("heading", { name: deal.codeName })).toBeVisible();
    await page.getByRole("tab", { name: "Documents" }).click();

    await page.getByLabel("Label (e.g. IM, Financials, VDR)").fill("VDR");
    await page.getByLabel("https link").fill("https://vdr.example.com/rooms/osprey");
    await page.getByRole("button", { name: "Add link" }).click();

    const link = page.getByRole("link", { name: "https://vdr.example.com/rooms/osprey" });
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");
    await expect(page.getByText("VDR", { exact: true })).toBeVisible();
  });

  // DEAL-03 c2 + c3: a stale save shows the conflict and the newer version; history shows who/old/new.
  test("a stale save shows a conflict with the newer version, and history records the change", async ({
    page,
    browser,
  }) => {
    await page.goto(`/deals/${deal.id}`);
    await expect(page.getByLabel("Estimated EV (EUR k)")).toBeVisible();

    const other = await browser.newContext();
    const headers = await signIn(other.request, PARTNER.email, PARTNER.password);
    const current = await (await other.request.get(`/api/v1/mandates/${deal.id}`)).json();
    const saved = await other.request.patch(`/api/v1/mandates/${deal.id}`, {
      headers,
      data: { version: current.version, estimated_ev: "15500" },
    });
    expect(saved.status()).toBe(200);
    await other.close();

    await page.getByLabel("Estimated EV (EUR k)").fill("99999");
    await page.getByRole("button", { name: "Save" }).click();

    await expect(page.getByText("Someone else saved first")).toBeVisible();
    await expect(page.getByText(/15500\.00/)).toBeVisible();
    await page.getByRole("button", { name: "Load the newer version" }).click();
    await expect(page.getByLabel("Estimated EV (EUR k)")).toHaveValue("15500.00");

    await page.getByRole("tab", { name: "History" }).click();
    const row = page.getByRole("row").filter({ hasText: "estimated_ev" }).first();
    await expect(row).toContainText(PARTNER.name);
    await expect(row).toContainText("12000.00");
    await expect(row).toContainText("15500.00");
  });
});
