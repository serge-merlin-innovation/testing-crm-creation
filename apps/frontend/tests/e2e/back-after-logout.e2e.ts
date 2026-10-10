import { expect, test } from "@playwright/test";
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH } from "@/lib/auth-routing";
import { MEMBER, signIn } from "./identities";

// AUTH-04 c2: after logout, the browser's Back button shows no cached deal or record page.
test("Back after logout shows the login page, not the cached page", async ({ page }) => {
  await page.goto(LOGIN_PATH);
  await signIn(page, MEMBER);
  await expect(page).toHaveURL(DEFAULT_AUTHENTICATED_PATH);
  await page.goto("/deals");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(LOGIN_PATH);

  await page.goBack();

  await expect(page).toHaveURL(new RegExp(`${LOGIN_PATH}(\\?|$)`));
  await expect(page.getByRole("button", { name: "Log out" })).toHaveCount(0);
});
