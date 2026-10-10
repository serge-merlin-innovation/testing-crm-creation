import { expect, test } from "@playwright/test";
import { ADMIN, MEMBER } from "./identities";

const RUN = Date.now().toString(36);

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
