import { expect, test } from "@playwright/test";
import { ADMIN, MEMBER } from "./identities";

// AUD-01 c3: compliance searches the audit log by user and action; others cannot open it.
test.describe("an admin with audit.read", () => {
  test.use({ storageState: ADMIN.storageState });

  test("searches the audit log by user and action", async ({ page }) => {
    const me: { id: number } = await (await page.request.get("/api/v1/users/me")).json();
    await page.goto("/");
    await page.getByRole("link", { name: "Audit log" }).click();
    await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
    await page.getByLabel("User ID").fill(String(me.id));
    await page.getByLabel("Action", { exact: true }).fill("login");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page.getByRole("status")).toContainText(/Entries found: [1-9]/);
    const rows = page.getByRole("row").filter({ has: page.getByRole("cell", { name: "login", exact: true }) });
    await expect(rows.first()).toBeVisible();
  });
});

test.describe("an analyst", () => {
  test.use({ storageState: MEMBER.storageState });

  test("has no audit log page or link", async ({ page }) => {
    await page.goto("/audit");
    await expect(page).not.toHaveURL(/\/audit$/);
    await expect(page.getByRole("link", { name: "Audit log" })).toHaveCount(0);
  });
});
