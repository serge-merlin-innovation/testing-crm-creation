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
const LETTER = `Round two ${RUN}`;

/** A deal with two approved buyers: one with a signed NDA (French contact), one without. */
async function seedDeal(browser: Browser) {
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const adminHeaders = await signInApi(admin, ADMIN);
  await inviteUser(browser, admin, adminHeaders, PARTNER, "Partner");
  const sector = await admin.post("/api/v1/picklists/", {
    headers: adminHeaders,
    data: {
      kind: "sector",
      code: `proc-${RUN}`,
      label_en: `Process sector ${RUN}`,
    },
  });
  expect(sector.status(), await sector.text()).toBe(201);
  const sectorId = (await sector.json()).id as number;
  await adminContext.close();

  const context = await browser.newContext();
  const request = context.request;
  const headers = await signInApi(request, PARTNER);
  const partner: { id: number } = await (
    await request.get("/api/v1/users/me")
  ).json();
  const countries: { id: number; code: string }[] = await (
    await request.get("/api/v1/picklists/?kind=country")
  ).json();
  const nl = countries.find((country) => country.code === "NL")!.id;
  const company = async (name: string, type: string) => {
    const response = await request.post("/api/v1/companies/", {
      headers,
      data: {
        name,
        type,
        country_id: nl,
        vat_or_registry_number: `${name}-${RUN}`,
        ignore_similar: true,
      },
    });
    expect(response.status(), await response.text()).toBe(201);
    return (await response.json()).id as number;
  };
  const client = await company(`Clientco ${TAG}`, "target");
  const mandate = await request.post("/api/v1/mandates/", {
    headers,
    data: {
      code_name: `Heron ${RUN.split("").reverse().join("")}`,
      client_id: client,
      type: "sell_side",
      sector_id: sectorId,
      lead_partner_id: partner.id,
      estimated_ev: "5000",
    },
  });
  expect(mandate.status(), await mandate.text()).toBe(201);
  const mandateId = (await mandate.json()).id as number;

  const buyer = async (
    name: string,
    contact: Record<string, unknown>,
    signed: boolean,
  ) => {
    const companyId = await company(name, "financial_investor");
    const person = await request.post("/api/v1/contacts/", {
      headers,
      data: {
        last_name: "Buyer",
        source: "Forum",
        company_id: companyId,
        ...contact,
      },
    });
    expect(person.status(), await person.text()).toBe(201);
    const added = await request.post(`/api/v1/mandates/${mandateId}/buyers`, {
      headers,
      data: {
        items: [
          {
            company_id: companyId,
            owner_id: partner.id,
            rationale: "Fit",
            contact_id: (await person.json()).id,
          },
        ],
      },
    });
    expect(added.status(), await added.text()).toBe(200);
    const buyerId = (await added.json()).added[0] as number;
    await request.patch(`/api/v1/mandates/${mandateId}/buyers/${buyerId}`, {
      headers,
      data: { approval: "approved" },
    });
    if (signed) {
      const nda = await request.put(
        `/api/v1/mandates/${mandateId}/buyers/${buyerId}/nda`,
        {
          headers,
          data: { sent_date: "2026-09-01", signed_date: "2026-09-10" },
        },
      );
      expect(nda.status(), await nda.text()).toBe(200);
    }
  };
  const signedName = `Sablon ${TAG} Partenaires`;
  const unsignedName = `Unsigned ${TAG} Capital`;
  await buyer(
    signedName,
    {
      first_name: "Claire",
      email: `claire.${RUN}@example.com`,
      language: "fr",
      salutation: "Chère Madame",
    },
    true,
  );
  await buyer(
    unsignedName,
    {
      first_name: "Uwe",
      email: `uwe.${RUN}@example.com`,
      language: "en",
      salutation: "Dear Mr",
    },
    false,
  );
  await context.close();
  return { mandateId, signedName, unsignedName };
}

let seeded: Awaited<ReturnType<typeof seedDeal>>;

test.use({ storageState: { cookies: [], origins: [] } });

test.beforeAll(async ({ browser }) => {
  seeded = await seedDeal(browser);
});

// ADM-07 c1 in the browser: an admin writes the letter in FR and EN.
test("an admin stores a letter template per language with merge fields", async ({
  browser,
}) => {
  const page = await browser.newPage();
  await page.goto(LOGIN_PATH);
  await signIn(page, ADMIN);
  await page.goto("/templates");
  for (const [language, body] of [
    ["FR", "{{salutation}} {{last_name}}, voici l'IM de {{code_name}}."],
    ["EN", "{{salutation}} {{last_name}}, here is the IM for {{code_name}}."],
  ]) {
    await page.getByLabel("Name").fill(LETTER);
    await page.locator("#template-language").click();
    await page.getByRole("option", { name: language }).click();
    await page.getByLabel("Subject").fill("{{code_name}}: IM");
    await page.getByLabel("Body").fill("{{fee}}");
    await expect(page.getByText("Unknown merge fields: fee")).toBeVisible();
    await page.getByLabel("Body").fill(body);
    await page.getByLabel(/References the IM/).check();
    await page.getByRole("button", { name: "Save template" }).click();
    await expect(
      page.getByRole("table", { name: "Letter and report templates" }),
    ).toContainText(language);
  }
});

// BUY-05 c1/c2/c4, BUY-06 c1/c2, BUY-07 c1, REP-05 c1, DEAL-03 c1 in the browser.
test("offers, comparison, a process letter, the funnel and the client report from the deal page", async ({
  browser,
}) => {
  const page = await browser.newPage();
  await page.goto(LOGIN_PATH);
  await signIn(page, PARTNER);
  await page.goto(`/deals/${seeded.mandateId}`);
  for (const tab of [
    "Summary",
    "Team",
    "Milestones",
    "Buyers",
    "Offers",
    "Funnel",
    "Letters and reports",
    "Activities and tasks",
    "Fees",
  ]) {
    await expect(
      page.getByRole("tab", { name: tab, exact: true }),
    ).toBeVisible();
  }

  await page.getByRole("tab", { name: "Offers" }).click();
  const record = async (buyer: string, ev: string) => {
    await page.locator("#offer-buyer").click();
    await page.getByRole("option", { name: buyer }).click();
    await page.getByLabel("EV (EUR m)").fill(ev);
    await page.getByLabel("Equity value (EUR m)").fill("30");
    await page.getByLabel("Conditions").fill("Confirmatory DD");
    await page.getByRole("button", { name: "Save offer" }).click();
  };
  await record(seeded.unsignedName, "35");
  await record(seeded.signedName, "40");
  await record(seeded.signedName, "45");
  const table = page.getByRole("table", { name: "Bid comparison" });
  await expect(table.locator("tbody tr").first()).toContainText(
    seeded.signedName,
  );
  await expect(
    table.locator(`[data-buyer="${seeded.signedName}"]`),
  ).toContainText("45.0");
  await expect(
    table.locator(`[data-buyer="${seeded.signedName}"]`),
  ).toContainText("v1: 40.0");

  await page.getByRole("tab", { name: "Letters and reports" }).click();
  await page.locator("#letter-template").click();
  await page.getByRole("option", { name: new RegExp(LETTER) }).click();
  await page.getByLabel(new RegExp(seeded.signedName)).check();
  await page.getByLabel(new RegExp(seeded.unsignedName)).check();
  await page.getByRole("button", { name: "Send letter" }).click();
  await expect(
    page.getByText(`Sent to: ${seeded.signedName} (fr)`),
  ).toBeVisible();
  await expect(page.locator('[data-excluded="no_signed_nda"]')).toContainText(
    seeded.unsignedName,
  );
  await expect(
    page.getByRole("table", { name: "Generated documents" }),
  ).toContainText(": IM");

  const report = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Generate client status report" })
    .click();
  expect((await report).suggestedFilename()).toMatch(/status-report\.pdf$/);

  await page.getByRole("tab", { name: "Funnel" }).click();
  await expect(page.locator('[data-step="approached"]')).toContainText("1");
  await expect(page.locator('[data-step="nda"]')).toContainText("100.0%");
  await expect(page.locator('[data-step="offers"]')).toHaveText("Offers1-");
  const funnel = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export to PDF" }).click();
  expect((await funnel).suggestedFilename()).toMatch(/-funnel\.pdf$/);

  await page.getByRole("tab", { name: "Activities and tasks" }).click();
  await expect(page.getByRole("region", { name: "Activities" })).toContainText(
    "Process letter sent",
  );
  await expect(page.getByRole("region", { name: "Activities" })).toContainText(
    "Client status report generated",
  );
});
