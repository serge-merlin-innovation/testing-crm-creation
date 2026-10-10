import { expect, test } from "@playwright/test";
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH } from "@/lib/auth-routing";
import { ADMIN, MEMBER } from "./identities";

const adminPaths = ["/users", "/permissions"];
const [adminPath] = adminPaths;
const authenticatedPath = "/profile";

test.describe("a signed-out visitor", () => {
  test("is sent to the login page carrying where they were headed", async ({ page }) => {
    test.skip(!authenticatedPath, "this app defines no authenticated page");

    await page.goto(authenticatedPath);

    await expect(page).toHaveURL(
      `${LOGIN_PATH}?next=${encodeURIComponent(authenticatedPath)}`,
    );
  });

  test("reaches the login page itself", async ({ page }) => {
    await page.goto(LOGIN_PATH);

    await expect(
      page.getByRole("button", { name: "Sign in securely" }),
    ).toBeVisible();
  });
});

test.describe("an admin", () => {
  test.use({ storageState: ADMIN.storageState });

  for (const path of adminPaths) {
    test(`reaches ${path}`, async ({ page }) => {
      await page.goto(path);

      await expect(page).toHaveURL(path);
    });
  }

  test("sees the permission matrix with roles as columns", async ({ page }) => {
    await page.goto("/permissions");

    for (const role of ["Admin", "Partner", "Director / Manager", "Analyst / Associate", "Compliance / Back-office", "Read-only"]) {
      await expect(page.getByRole("columnheader", { name: role, exact: true })).toBeVisible();
    }
    await expect(page.getByRole("cell", { name: "audit.read", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Export CSV" })).toBeVisible();
  });
});

test.describe("an analyst", () => {
  test.use({ storageState: MEMBER.storageState });

  test("is refused an admin page and lands on the landing page, not on login", async ({
    page,
  }) => {
    test.skip(!adminPath, "this app defines no admin page");

    await page.goto(adminPath);

    await expect(page).toHaveURL(DEFAULT_AUTHENTICATED_PATH);
  });

  test("is never offered a link to a page it cannot enter", async ({ page }) => {
    await page.goto(DEFAULT_AUTHENTICATED_PATH);

    const hrefs = await page
      .getByRole("navigation", { name: "Primary" })
      .getByRole("link")
      .evaluateAll((links) => links.map((link) => link.getAttribute("href")));

    // Non-empty proves the real session reached the navbar; an anonymous reader renders nothing.
    expect(hrefs.length).toBeGreaterThan(0);

    // Deliberately only the admin audience. Deriving the full forbidden set would mean calling
    // satisfiesAudience, the function the navbar is already built from, and proving nothing.
    for (const path of adminPaths) {
      expect(hrefs).not.toContain(path);
    }
  });
});
