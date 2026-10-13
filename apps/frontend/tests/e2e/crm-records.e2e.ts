import { expect, test } from "@playwright/test";
import { ADMIN, MEMBER, runId } from "./identities";

const RUN = runId();

test.describe("an analyst", () => {
  test.use({ storageState: MEMBER.storageState });

  test("creates a company and finds it by name", async ({ page }) => {
    await page.goto("/companies");
    await page.getByLabel("Name").fill(`Zephyrine Optics ${RUN}`);
    await page.getByLabel("Country").click();
    await page.getByRole("option", { name: "Netherlands" }).click();
    await page.getByLabel("VAT or registry number").fill(`NW-${RUN}`);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Company created.");

    await page.getByRole("textbox", { name: "Search" }).fill(`zephyrine optics ${RUN}`);
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByRole("cell", { name: `Zephyrine Optics ${RUN}` })).toBeVisible();
  });

  test("creates a contact with an inline phone error first", async ({ page }) => {
    await page.goto("/contacts");
    await page.getByLabel("First name").fill("Ines");
    await page.getByLabel("Last name").fill(`Maes${RUN}`);
    await page.getByLabel("Phone").fill("12");
    await page.getByLabel("Source").fill("E2E");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Invalid phone number")).toBeVisible();

    await page.getByLabel("Phone").fill("+32 470 12 34 56");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Contact created.");
    await expect(page.getByRole("cell", { name: `Ines Maes${RUN}` })).toBeVisible();
  });

  test("records a contact's language and opt-out and a company's language", async ({ page }) => {
    await page.goto("/contacts");
    await page.getByLabel("First name").fill("Odile");
    await page.getByLabel("Last name").fill(`Optout${RUN}`);
    await page.getByLabel("Source").fill("E2E");
    await page.getByLabel("Language").click();
    await page.getByRole("option", { name: "French" }).click();
    await page.getByLabel("Salutation").fill("Chère Madame");
    await page.getByLabel("No marketing mailings (opt-out)").check();
    await page.getByLabel("Do not contact").check();
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Contact created.");
    const contacts = await (await page.request.get(`/api/v1/contacts/?q=Optout${RUN}`)).json();
    expect(contacts[0]).toMatchObject({
      language: "fr",
      salutation: "Chère Madame",
      marketing_opt_out: true,
      do_not_contact: true,
    });

    await page.goto("/companies");
    await page.getByLabel("Name").fill(`Lingua Partners ${RUN}`);
    await page.getByLabel("Country").click();
    await page.getByRole("option", { name: "Netherlands" }).click();
    await page.getByLabel("VAT or registry number").fill(`LG-${RUN}`);
    await page.getByLabel("Language").click();
    await page.getByRole("option", { name: "Dutch" }).click();
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Company created.");
    const companies = await (await page.request.get(`/api/v1/companies/?q=Lingua Partners ${RUN}`)).json();
    expect(companies[0]).toMatchObject({ language: "nl" });
  });

  test("is not offered the picklists page", async ({ page }) => {
    await page.goto("/overview");
    await expect(page.getByRole("link", { name: "Picklists" })).toHaveCount(0);
  });
});

test.describe("an admin", () => {
  test.use({ storageState: ADMIN.storageState });

  test("adds a sector and sees it flagged until translated", async ({ page }) => {
    await page.goto("/picklists");
    await page.getByLabel("Code").fill(`s-${RUN}`);
    await page.getByLabel("Label (EN)").fill(`Sector ${RUN}`);
    await page.getByRole("button", { name: "Add" }).click();

    const row = page.getByRole("row").filter({ hasText: `Sector ${RUN}` });
    await expect(row).toContainText("Missing FR or NL");
  });

  // ROLE-01 c2: an Admin who is not staffed has no Deals link and sees no deal.
  test("is not offered deals", async ({ page }) => {
    await page.goto("/overview");
    await expect(page.getByRole("link", { name: "Deals" })).toHaveCount(0);
  });
});

/** A valid Belgian enterprise number: the last two digits are 97 minus the first eight mod 97. */
function enterpriseNumber(): string {
  const base = `0${Array.from({ length: 7 }, () => Math.floor(Math.random() * 10)).join("")}`;
  const check = 97 - (Number(base) % 97);
  return `${base}${String(check).padStart(2, "0")}`;
}

async function newCompany(
  page: import("@playwright/test").Page,
  name: string,
  country = "Netherlands",
): Promise<number> {
  await page.goto("/companies");
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Country").click();
  await page.getByRole("option", { name: country }).click();
  await page.getByLabel("VAT or registry number").fill(`R-${runId()}`);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Company created.");
  const found: { id: number; name: string }[] = await (
    await page.request.get(`/api/v1/companies/?q=${encodeURIComponent(name)}`)
  ).json();
  return found.find((company) => company.name === name)!.id;
}

test.describe("company and contact records", () => {
  test.use({ storageState: MEMBER.storageState });

  test("offers each possible duplicate as a link to open instead", async ({ page }) => {
    const name = `Duplicata Holding ${RUN}`;
    const id = await newCompany(page, name);

    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Country").click();
    await page.getByRole("option", { name: "Netherlands" }).click();
    await page.getByLabel("VAT or registry number").fill(`D2-${RUN}`);
    await page.getByRole("button", { name: "Save" }).click();

    const link = page.getByRole("alert").getByRole("link", { name, exact: true });
    await expect(link).toHaveAttribute("href", `/companies/${id}`);
    await link.click();
    await expect(page.getByRole("heading", { name })).toBeVisible();
  });

  test("pre-fills a Belgian company from the KBO/BCE register", async ({ page, request }) => {
    const number = enterpriseNumber();
    const legalName = `Kbo Prefill ${RUN}`;
    const faked = await request.put("/api/v1/test-hooks/registers", {
      data: {
        entries: { [number]: { legal_name: legalName, address: "Rue Royale 1, 1000 Brussels", legal_form: "SA", nace_code: "62010" } },
      },
    });
    expect(faked.status(), await faked.text()).toBe(200);

    await page.goto("/companies");
    await page.getByLabel("Country").click();
    await page.getByRole("option", { name: "Belgium" }).click();
    await page.getByLabel("Enterprise number (KBO/BCE)").fill(number);
    await page.getByRole("button", { name: "Look up in KBO/BCE" }).click();
    await expect(page.getByLabel("Name")).toHaveValue(legalName);
    await expect(page.getByLabel("Address")).toHaveValue("Rue Royale 1, 1000 Brussels");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Company created.");

    const created = await (await page.request.get(`/api/v1/companies/?q=${encodeURIComponent(legalName)}`)).json();
    expect(created[0]).toMatchObject({ name: legalName, legal_form: "SA", nace_code: "62010" });
  });

  test("imports NBB financials, overrides a figure in another currency and shows the group tree on both companies", async ({
    page,
    request,
  }) => {
    const number = enterpriseNumber();
    const name = `Nbb Figures ${RUN}`;
    await request.put("/api/v1/test-hooks/registers", {
      data: {
        entries: { [number]: { legal_name: name } },
        accounts: {
          [number]: [2023, 2024, 2025, 2022].map((year) => ({
            year,
            filed_on: `${year + 1}-06-30`,
            revenue: String(1000 + year - 2020),
            ebitda: "200",
          })),
        },
      },
    });
    await page.goto("/companies");
    await page.getByLabel("Country").click();
    await page.getByRole("option", { name: "Belgium" }).click();
    await page.getByLabel("Enterprise number (KBO/BCE)").fill(number);
    await page.getByRole("button", { name: "Look up in KBO/BCE" }).click();
    await expect(page.getByLabel("Name")).toHaveValue(name);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Company created.");
    const parentName = `Nbb Parent ${RUN}`;
    await newCompany(page, parentName);

    await page.getByRole("textbox", { name: "Search", exact: true }).fill(name);
    await page.getByRole("button", { name: "Search" }).click();
    await page.getByRole("link", { name, exact: true }).click();
    await expect(page.getByRole("heading", { name })).toBeVisible();

    await page.getByRole("button", { name: "Import from NBB" }).click();
    const figures = page.getByRole("table", { name: "Financials (EUR k)" });
    await expect(figures.getByRole("row")).toHaveCount(4);
    await expect(figures.getByRole("row").nth(1)).toContainText("2025");
    await expect(figures).not.toContainText("2022");

    await page.getByLabel("Year").fill("2025");
    await page.getByLabel("Revenue").fill("2000");
    await page.getByLabel("Currency").fill("USD");
    await page.getByLabel("EUR rate").fill("0.9");
    await page.getByRole("button", { name: "Save year" }).click();
    const year2025 = figures.getByRole("row").filter({ hasText: "2025" });
    await expect(year2025).toContainText("1,800");
    await expect(year2025).toContainText("Imported: 1,005");
    await expect(year2025).toContainText("2,000 USD");

    await page.getByLabel("Find Parent company").fill(parentName);
    await page.getByLabel("Parent company", { exact: true }).click();
    await page.getByRole("option", { name: parentName }).click();
    await page.getByRole("button", { name: "Save parent" }).click();
    const tree = page.getByRole("tree", { name: "Group" });
    await expect(tree.getByRole("treeitem", { name: parentName })).toBeVisible();
    await expect(tree.getByRole("treeitem", { name })).toBeVisible();

    await tree.getByRole("link", { name: parentName }).click();
    await expect(page.getByRole("heading", { name: parentName })).toBeVisible();
    await expect(page.getByRole("tree", { name: "Group" }).getByRole("treeitem", { name })).toBeVisible();

    await request.put("/api/v1/test-hooks/registers", { data: {} });
  });

  test("links a portfolio company to a fund from the investor profile", async ({ page }) => {
    const fund = `Portfolio Fund ${RUN}`;
    const holding = `Portfolio Bakery ${RUN}`;
    await newCompany(page, holding);
    await page.getByLabel("Name").fill(fund);
    await page.getByLabel("Type").click();
    await page.getByRole("option", { name: "financial_investor" }).click();
    await page.getByLabel("Country").click();
    await page.getByRole("option", { name: "Netherlands" }).click();
    await page.getByLabel("VAT or registry number").fill(`PF-${RUN}`);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Company created.");

    await page.getByRole("textbox", { name: "Search", exact: true }).fill(fund);
    await page.getByRole("button", { name: "Search" }).click();
    await page.getByRole("link", { name: fund, exact: true }).click();
    const profile = page.getByRole("region", { name: "Investor profile" });
    await profile.getByLabel("Find Link a portfolio company").fill(holding);
    await profile.getByLabel("Link a portfolio company", { exact: true }).click();
    await page.getByRole("option", { name: holding }).click();
    await profile.getByRole("button", { name: "Link" }).click();
    await expect(profile.getByText(holding)).toBeVisible();
  });

  test("moves a contact to another company and keeps the old role as history", async ({ page }) => {
    const first = `Aldermoor Logistics ${RUN}`;
    const second = `Quintavale Foods ${runId()}`;
    await newCompany(page, first);
    await newCompany(page, second);
    await page.goto("/contacts");
    await page.getByLabel("First name").fill("Hanne");
    await page.getByLabel("Last name").fill(`Mover${RUN}`);
    await page.getByLabel("Source").fill("E2E");
    await page.getByLabel("Find Company").fill(first);
    await page.getByLabel("Company", { exact: true }).click();
    await page.getByRole("option", { name: first }).click();
    await page.getByLabel("Function").fill("CFO");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Contact created.");

    await page.getByRole("textbox", { name: "Search", exact: true }).fill(`Mover${RUN}`);
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await page.getByRole("link", { name: `Hanne Mover${RUN}` }).click();
    await expect(page.getByRole("heading", { level: 1, name: `Hanne Mover${RUN}` })).toBeVisible();
    await page.getByLabel("Find Company").fill(second);
    await page.getByLabel("Company", { exact: true }).click();
    await page.getByRole("option", { name: second }).click();
    await page.getByLabel("Function").fill("CEO");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByRole("status")).toHaveText("Contact saved.");

    const history = page.getByRole("table", { name: "Employment history" });
    await expect(history.getByRole("row").filter({ hasText: first })).toContainText("CFO");
    await expect(history.getByRole("row").filter({ hasText: second })).toContainText("CEO");
  });
});
