import { expect, test } from "@playwright/test";
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH } from "@/lib/auth-routing";
import { MEMBER, submitCredentials } from "./identities";

test("logging out revokes the session and closes the gated pages behind it", async ({
  page,
}) => {
  // Signs in fresh rather than using the banked member session: logging out revokes the session
  // server-side, and every other spec shares that one.
  await page.goto(LOGIN_PATH);
  await submitCredentials(page, MEMBER);
  await expect(page).toHaveURL(DEFAULT_AUTHENTICATED_PATH);

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(LOGIN_PATH);

  await page.goto(DEFAULT_AUTHENTICATED_PATH);

  await expect(page).toHaveURL(
    `${LOGIN_PATH}?next=${encodeURIComponent(DEFAULT_AUTHENTICATED_PATH)}`,
  );
});
