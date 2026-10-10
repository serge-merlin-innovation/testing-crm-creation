import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { LOGIN_PATH } from "@/lib/auth-routing";
import { PAGE_AUDIENCE } from "@/lib/page-audience";
import { ADMIN, inviteUser, signIn, signInApi, runId } from "./identities";

// NFR-04 c2 (375 px, no horizontal scroll), c3 (WCAG 2.1 AA via axe), c4 (Belgian formats) and
// c1 (FR/NL labels) over every page the app serves, as the people who use each page.

const RUN = runId();
const PARTNER = {
  firstName: "Paulien",
  lastName: "Vennoot",
  email: `e2e.a11y.${RUN}@example.com`,
  password: "Velvet-Harbour-58-Beacon",
};
const PHONE = { width: 375, height: 812 };
const DESKTOP = { width: 1280, height: 900 };

type Seeded = { dealId: number; opportunityId: number | null; companyId: number; contactId: number };
let seeded: Seeded;

async function seed(browser: Browser): Promise<Seeded> {
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const adminHeaders = await signInApi(admin, ADMIN);
  await inviteUser(browser, admin, adminHeaders, PARTNER, "Partner");
  const sector = await admin.post("/api/v1/picklists/", {
    headers: adminHeaders,
    data: { kind: "sector", code: `a11y-${RUN}`, label_en: `Accessibility ${RUN}`, label_fr: `Accessibilité ${RUN}`, label_nl: `Toegankelijkheid ${RUN}` },
  });
  expect(sector.status(), await sector.text()).toBe(201);
  const sectorId = (await sector.json()).id as number;
  await adminContext.close();

  const context = await browser.newContext();
  const request = context.request;
  const headers = await signInApi(request, PARTNER);
  const me: { id: number } = await (await request.get("/api/v1/users/me")).json();
  const countries: { id: number; code: string }[] = await (await request.get("/api/v1/picklists/?kind=country")).json();
  const company = await request.post("/api/v1/companies/", {
    headers,
    data: {
      name: `Zuidrand Werken ${RUN.toUpperCase()}`,
      type: "target",
      country_id: countries.find((country) => country.code === "NL")!.id,
      vat_or_registry_number: `NL-A11Y-${RUN}`,
      ignore_similar: true,
    },
  });
  expect(company.status(), await company.text()).toBe(201);
  const companyId = (await company.json()).id as number;
  const contact = await request.post("/api/v1/contacts/", {
    headers,
    data: { first_name: "Lotte", last_name: `Peeters${RUN}`, email: `lotte.${RUN}@example.be`, source: "E2E" },
  });
  expect(contact.status(), await contact.text()).toBe(201);
  const contactId = (await contact.json()).id as number;
  const mandate = await request.post("/api/v1/mandates/", {
    headers,
    data: {
      code_name: `Heron ${RUN.split("").reverse().join("")}`,
      client_id: companyId,
      type: "sell_side",
      sector_id: sectorId,
      lead_partner_id: me.id,
      estimated_ev: "1234567",
    },
  });
  expect(mandate.status(), await mandate.text()).toBe(201);
  const dealId = (await mandate.json()).id as number;
  const milestone = await request.post(`/api/v1/mandates/${dealId}/milestones`, {
    headers,
    data: { name: "IM sent", planned_date: "2027-03-07" },
  });
  expect(milestone.status(), await milestone.text()).toBe(201);
  const opportunity = await request.post("/api/v1/origination/opportunities", {
    headers,
    data: { company_id: companyId, type: "sell_side", estimated_ev: "5000" },
  });
  const opportunityId = opportunity.ok() ? ((await opportunity.json()).id as number) : null;
  await context.close();
  return { dealId, opportunityId, companyId, contactId };
}

/** Saves the account's language over the API, then signs in through a browser with no language
 *  cookie (as on a new device), which must then show the saved language. */
async function signedInContext(browser: Browser, identity: { email: string; password: string }, language: string) {
  const api = await browser.newContext();
  const headers = await signInApi(api.request, identity);
  const me: { id: number } = await (await api.request.get("/api/v1/users/me")).json();
  const saved = await api.request.patch(`/api/v1/users/${me.id}`, { data: { language }, headers });
  expect(saved.status(), await saved.text()).toBe(200);
  await api.close();
  const context = await browser.newContext({ extraHTTPHeaders: { "Accept-Language": "en" } });
  const page = await context.newPage();
  await page.goto(LOGIN_PATH);
  await signIn(page, identity);
  await expect(page).not.toHaveURL(new RegExp(LOGIN_PATH));
  await page.close();
  return context;
}

/** Every listed page plus the detail pages behind them. Public pages are checked signed out. */
function pagesFor(who: "admin" | "partner"): string[] {
  const listed = Object.entries(PAGE_AUDIENCE)
    .filter(([, audience]) => audience.kind !== "public")
    .map(([path]) => path);
  const admin = ["/users", "/permissions", "/settings", "/picklists", "/templates", "/imports", "/stage-criteria", "/profile", "/overview", "/merge", "/exports", "/privacy", "/access", "/search"];
  if (who === "admin") {
    return listed.filter((path) => admin.includes(path));
  }
  return [
    ...listed.filter((path) => !admin.includes(path) || ["/profile", "/overview", "/search", "/access", "/exports", "/privacy", "/merge"].includes(path)),
    `/deals/${seeded.dealId}`,
    ...(seeded.opportunityId ? [`/origination/${seeded.opportunityId}`] : []),
  ].filter((path) => !["/conflict-reviews", "/settings", "/users", "/permissions", "/picklists", "/templates", "/imports", "/stage-criteria"].includes(path));
}

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await expect(page.locator("main").first()).toBeVisible();
}

async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

async function audit(page: Page, path: string): Promise<string[]> {
  const problems: string[] = [];
  const overflow = await horizontalOverflow(page);
  if (overflow > 0) {
    problems.push(`${path}: scrolls ${overflow}px sideways`);
  }
  for (const violation of await axeViolations(page)) {
    problems.push(`${path}: ${violation.id} (${violation.impact}) ${violation.targets.join(" | ")} ${violation.summary}`);
  }
  return problems;
}

async function axeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  return results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    targets: violation.nodes.slice(0, 3).map((node) => node.target.join(" ")),
    summary: violation.nodes[0]?.failureSummary?.split("\n").slice(1, 2).join(" ") ?? "",
  }));
}

test.describe.configure({ mode: "default" });

test.beforeAll(async ({ browser }) => {
  seeded = await seed(browser);
});

for (const viewport of [PHONE, DESKTOP]) {
  test.describe(`at ${viewport.width} px`, () => {
    test("public pages: no horizontal scroll, WCAG 2.1 AA", async ({ browser }) => {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();
      const problems: string[] = [];
      for (const path of ["/login", "/reset-password", "/accept-invitation"]) {
        await page.goto(path);
        await settle(page);
        problems.push(...(await audit(page, path)));
      }
      expect(problems).toEqual([]);
      await context.close();
    });

    for (const who of ["admin", "partner"] as const) {
      test(`${who} pages: no horizontal scroll, WCAG 2.1 AA`, async ({ browser }) => {
        const context: BrowserContext = await signedInContext(browser, who === "admin" ? ADMIN : PARTNER, "en");
        const page = await context.newPage();
        await page.setViewportSize(viewport);
        const problems: string[] = [];
        for (const path of pagesFor(who)) {
          await page.goto(path);
          await settle(page);
          problems.push(...(await audit(page, path)));
        }
        expect(problems).toEqual([]);
        await context.close();
      });
    }
  });
}

test("a French-speaking partner reads French labels and Belgian formats", async ({ browser }) => {
  const context = await signedInContext(browser, PARTNER, "fr");
  const page = await context.newPage();
  await page.goto(`/deals/${seeded.dealId}`);
  await settle(page);
  await expect(page.locator("html")).toHaveAttribute("lang", "fr");
  await expect(page.getByRole("link", { name: "Dossiers" }).first()).toBeVisible();
  await page.getByRole("tab", { name: "Jalons" }).click();
  await expect(page.getByText("07/03/2027")).toBeVisible();
  await page.goto("/deals");
  await settle(page);
  await page.getByRole("tab", { name: "Liste" }).click();
  await expect(page.getByText("1.234.567")).toBeVisible();
  await context.close();
});

test("choosing Nederlands on Profile switches the whole app and is saved for next time", async ({ browser }) => {
  const context = await signedInContext(browser, PARTNER, "en");
  const page = await context.newPage();
  await page.goto("/profile");
  await settle(page);
  const saved = page.waitForResponse((response) => response.url().includes("/api/v1/users/") && response.request().method() === "PATCH");
  await page.getByLabel("Language").click();
  await page.getByRole("option", { name: "Nederlands" }).click();
  expect((await saved).status()).toBe(200);
  await expect(page.locator("html")).toHaveAttribute("lang", "nl");
  await expect(page.getByRole("heading", { name: "Taal" })).toBeVisible();

  // A fresh browser with no cookie still opens in Dutch: the choice lives on the account.
  const fresh = await browser.newContext();
  const freshPage = await fresh.newPage();
  await freshPage.goto(LOGIN_PATH);
  await signIn(freshPage, PARTNER);
  await freshPage.goto("/profile");
  await expect(freshPage.locator("html")).toHaveAttribute("lang", "nl");
  await fresh.close();

  await page.getByLabel("Taal").click();
  await page.getByRole("option", { name: "English" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await context.close();
});
