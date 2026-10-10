import { expect, test } from "@playwright/test";
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH } from "@/lib/auth-routing";
import { MEMBER, signIn, submitCredentials } from "./identities";

// Serial so a failure stops the group: every extra attempt spends part of the shared login-lockout
// budget, and five failed sign-ins through this server lock out everyone (CONSTITUTION.md § 6).
test.describe.configure({ mode: "serial" });

const returnToPath = "/profile";

test("signs in and lands on the default authenticated page", async ({ page }) => {
  await page.goto(LOGIN_PATH);
  await signIn(page, MEMBER);

  await expect(page).toHaveURL(DEFAULT_AUTHENTICATED_PATH);
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
});

test("returns to the page the visitor was headed for", async ({ page }) => {
  await page.goto(`${LOGIN_PATH}?next=${encodeURIComponent(returnToPath)}`);
  await signIn(page, MEMBER);

  await expect(page).toHaveURL(returnToPath);
});

// The only failed sign-in in the suite. It submits an email that does not exist, so the
// per-account lockout counter never lands on an account the other specs depend on.
test("refuses unknown credentials without leaving the login page", async ({ page }) => {
  await page.goto(LOGIN_PATH);
  await submitCredentials(page, {
    email: "nosuchperson@example.com",
    password: "WrongPassword!1",
  });

  // Scoped to the form: Next injects its own role="alert" route announcer into every page, so an
  // unscoped getByRole("alert") is always ambiguous here.
  await expect(page.locator("form").getByRole("alert")).toContainText(
    "Invalid email or password",
  );
  await expect(page).toHaveURL(LOGIN_PATH);
});

test("shows the last sign-in date, IP and device on the profile", async ({ page }) => {
  await page.goto(`${LOGIN_PATH}?next=${encodeURIComponent(returnToPath)}`);
  await signIn(page, MEMBER);
  await expect(page).toHaveURL(returnToPath);

  const card = page.getByRole("table");
  await expect(card.getByRole("row", { name: /IP address/ })).not.toContainText("Never");
  await expect(card.getByRole("row", { name: /Device/ })).toContainText("Chrome");
  await expect(card.getByRole("row", { name: /Last sign-in/ })).toContainText(/\d{2}\/\d{2}\/\d{4}/);
});
