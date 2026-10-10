import { expect, test, type Browser, type Page } from "@playwright/test";
import { LOGIN_PATH } from "@/lib/auth-routing";
import { ADMIN, MEMBER, inviteUser, signIn, signInApi } from "./identities";
import { currentCode } from "./totp";

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
const RUN = Date.now().toString(36);
const CODE_NAME = `Kestrel ${RUN.split("").reverse().join("")}`;

async function seedDeal(browser: Browser) {
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const adminHeaders = await signInApi(admin, ADMIN);
  await inviteUser(browser, admin, adminHeaders, PARTNER, "Partner");
  await inviteUser(browser, admin, adminHeaders, COMPLIANCE, "Compliance / Back-office");
  const sector = await admin.post("/api/v1/picklists/", {
    headers: adminHeaders,
    data: { kind: "sector", code: `wc-${RUN}`, label_en: `Wall crossing sector ${RUN}` },
  });
  expect(sector.status(), await sector.text()).toBe(201);
  const sectorId = (await sector.json()).id as number;
  await adminContext.close();

  const context = await browser.newContext();
  const request = context.request;
  const headers = await signInApi(request, PARTNER);
  const partner: { id: number } = await (await request.get("/api/v1/users/me")).json();
  const countries: { id: number; code: string }[] = await (await request.get("/api/v1/picklists/?kind=country")).json();
  const client = await request.post("/api/v1/companies/", {
    headers,
    data: {
      name: `Zephyr Tools ${RUN.toUpperCase()}`,
      type: "target",
      country_id: countries.find((country) => country.code === "NL")!.id,
      vat_or_registry_number: `wc-${RUN}`,
      ignore_similar: true,
    },
  });
  expect(client.status(), await client.text()).toBe(201);
  const deal = await request.post("/api/v1/mandates/", {
    headers,
    data: {
      code_name: CODE_NAME,
      client_id: (await client.json()).id,
      type: "sell_side",
      sector_id: sectorId,
      lead_partner_id: partner.id,
      estimated_ev: "5000",
    },
  });
  expect(deal.status(), await deal.text()).toBe(201);
  const created = (await deal.json()) as { id: number };
  await context.close();
  return created;
}

async function signedIn(browser: Browser, identity: { email: string; password: string }): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto(LOGIN_PATH);
  await signIn(page, identity);
  await page.goto("/access");
  return page;
}

let deal: { id: number };

test.use({ storageState: { cookies: [], origins: [] } });

test.beforeAll(async ({ browser }) => {
  deal = await seedDeal(browser);
});

// AUTHZ-04 c1/c2/c6 + AUTHZ-08 c1/c3 + AUTH-02 c5 in the browser.
test("a user asks to cross the wall, the partner comments, compliance approves; an admin breaks the glass read-only", async ({
  browser,
}) => {
  const member = await signedIn(browser, MEMBER);
  await member.getByLabel("Code name").fill(CODE_NAME.toLowerCase());
  await member.getByLabel("Reason").fill("Sector expertise for the buyer list");
  await member.getByRole("button", { name: "Send request" }).click();
  await expect(member.getByText("Request sent.", { exact: false })).toBeVisible();
  await expect(member.locator(`[data-request="${CODE_NAME}"]`)).toContainText("Pending");

  const partner = await signedIn(browser, PARTNER);
  await partner.locator(`[data-pending="${CODE_NAME}"]`).getByRole("button", { name: "Open" }).click();
  await expect(partner.getByText("You can comment. Compliance approves or rejects.")).toBeVisible();
  await expect(partner.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
  await partner.getByRole("button", { name: "Recommend approval" }).click();
  await expect(partner.getByText("Approved by Pieter Partner")).toBeVisible();

  const compliance = await signedIn(browser, COMPLIANCE);
  await compliance.locator(`[data-pending="${CODE_NAME}"]`).getByRole("button", { name: "Open" }).click();
  await expect(compliance.getByText("The requester is on no conflicting deal.")).toBeVisible();
  await expect(compliance.getByText("Approved by Pieter Partner")).toBeVisible();
  await compliance.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(compliance.locator(`[data-pending="${CODE_NAME}"]`)).toHaveCount(0);

  await member.reload();
  await expect(member.locator(`[data-request="${CODE_NAME}"]`)).toContainText("Approved");
  await member.goto(`/deals/${deal.id}`);
  await expect(member.getByRole("heading", { name: CODE_NAME })).toBeVisible();

  const admin = await signedIn(browser, ADMIN);
  const glass = admin.getByRole("form", { name: "Break-glass access" });
  await glass.getByLabel("Code name").fill(CODE_NAME);
  await glass.getByLabel("Reason").fill("Fix a corrupted EV");
  await admin.getByLabel("Authentication code").fill("000000");
  await admin.getByRole("button", { name: "Open read-only" }).click();
  await expect(admin.getByText("Enter your authentication code", { exact: false })).toBeVisible();
  await admin.getByLabel("Authentication code").fill(currentCode(ADMIN.email));
  await admin.getByRole("button", { name: "Open read-only" }).click();
  await expect(admin.getByText("Read-only access until", { exact: false })).toBeVisible();
  const exported = await admin.request.get(`/api/v1/mandates/${deal.id}/export`);
  expect(exported.status()).toBe(403);
  await admin.goto(`/deals/${deal.id}`);
  await expect(admin.getByRole("heading", { name: CODE_NAME })).toBeVisible();
});
