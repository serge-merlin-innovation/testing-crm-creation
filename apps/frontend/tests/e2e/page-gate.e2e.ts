import { expect, test } from "@playwright/test";
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH } from "@/lib/auth-routing";
import { MEMBER, SUPERUSER, pathsFor } from "./identities";

const adminPaths = pathsFor("admin");
const [adminPath] = adminPaths;
const [authenticatedPath] = pathsFor("authenticated");

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

test.describe("a superuser satisfies every audience", () => {
  test.use({ storageState: SUPERUSER.storageState });

  for (const kind of ["authenticated", "admin", "role"] as const) {
    const [path] = pathsFor(kind);

    test(`reaches the ${kind} page`, async ({ page }) => {
      test.skip(!path, `this app defines no ${kind} page`);

      await page.goto(path);

      await expect(page).toHaveURL(path);
    });
  }
});

test.describe("a member holding the default role", () => {
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
