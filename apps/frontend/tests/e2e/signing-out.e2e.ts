import { expect, test } from "@playwright/test";
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH } from "@/lib/auth-routing";
import { MEMBER, signIn } from "./identities";

test("logging out revokes the session and closes the gated pages behind it", async ({
  page,
}) => {
  // Signs in fresh rather than using the banked member session: logging out revokes the session
  // server-side, and every other spec shares that one.
  await page.goto(LOGIN_PATH);
  await signIn(page, MEMBER);
  await expect(page).toHaveURL(DEFAULT_AUTHENTICATED_PATH);

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(LOGIN_PATH);

  await page.goto(DEFAULT_AUTHENTICATED_PATH);

  await expect(page).toHaveURL(
    `${LOGIN_PATH}?next=${encodeURIComponent(DEFAULT_AUTHENTICATED_PATH)}`,
  );
});

// AUTH-04 c4: Log out with unsaved changes warns first; Stay keeps the session and the edit.
test("logging out with unsaved changes asks first", async ({ page }) => {
  await page.goto(LOGIN_PATH);
  await signIn(page, MEMBER);
  await expect(page).toHaveURL(DEFAULT_AUTHENTICATED_PATH);

  await page.goto("/contacts");
  const field = page.getByLabel("First name");
  await field.fill("Unsaved draft");
  await page.getByRole("button", { name: "Log out" }).click();

  const dialog = page.getByRole("alertdialog");
  await expect(dialog.getByRole("heading", { name: "Leave with unsaved changes?" })).toBeVisible();
  await dialog.getByRole("button", { name: "Stay" }).click();
  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL("/contacts");
  await expect(field).toHaveValue("Unsaved draft");
  await expect(page.getByRole("navigation", { name: "Main menu" })).toBeVisible();
});
