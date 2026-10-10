import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { getPrimaryNavigation, getAccountNavigation, allNavigationHrefs } from "@/lib/app-navigation";
import { ADMIN, MEMBER } from "./identities";

const WCAG_21_AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const PHONE = { width: 375, height: 812 };

/**
 * The analyst walks the record pages it is offered; the admin walks every navigation route, so a
 * page an admin is refused is still checked in the state that admin sees.
 */
function routesFor(email: string, permissions: string[]): string[] {
  if (email === ADMIN.email) return allNavigationHrefs();
  const viewer = { isAuthenticated: true, roleName: null, permissions };
  return [...getPrimaryNavigation(viewer), ...getAccountNavigation(viewer)].map((item) => item.href);
}

async function permissionsOf(page: Page): Promise<string[]> {
  const me = await (await page.request.get("/api/v1/users/me")).json();
  return me.permissions ?? [];
}

async function axeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG_21_AA).analyze();
  return results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target).join(" | ")}`);
}

async function overflowsHorizontally(page: Page): Promise<boolean> {
  return page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
}

for (const identity of [MEMBER, ADMIN]) {
  test.describe(`pages as ${identity.email}`, () => {
    test.use({ storageState: identity.storageState });

    // NFR-04 c3: WCAG 2.1 AA, checked by axe on every page in the navigation.
    test("every page passes axe WCAG 2.1 AA", async ({ page }) => {
      await page.goto("/overview");
      const found: string[] = [];
      for (const href of routesFor(identity.email, await permissionsOf(page))) {
        await page.goto(href);
        await page.waitForLoadState("networkidle");
        found.push(...(await axeViolations(page)).map((violation) => `${href} ${violation}`));
      }
      expect(found).toEqual([]);
    });

    // NFR-04 c2: usable at 375 px, no page scrolls sideways.
    test("every page fits a 375 px screen", async ({ page }) => {
      await page.setViewportSize(PHONE);
      await page.goto("/overview");
      const overflowing: string[] = [];
      for (const href of routesFor(identity.email, await permissionsOf(page))) {
        await page.goto(href);
        await page.waitForLoadState("networkidle");
        if (await overflowsHorizontally(page)) overflowing.push(href);
      }
      expect(overflowing).toEqual([]);
    });
  });
}
