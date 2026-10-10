import { expect, test as setup, type Page } from "@playwright/test";
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH } from "@/lib/auth-routing";
import {
  MEMBER,
  MEMBER_REGISTRATION,
  SUPERUSER,
  submitCredentials,
  type Identity,
} from "./identities";

async function signInAndBankSession(page: Page, identity: Identity) {
  await page.goto(LOGIN_PATH);
  await submitCredentials(page, identity);

  await expect(
    page,
    `${identity.username} could not sign in. If this fork changed the seeded superuser, set ` +
      `E2E_SUPERUSER_USERNAME and E2E_SUPERUSER_PASSWORD.`,
  ).toHaveURL(DEFAULT_AUTHENTICATED_PATH);

  await page.context().storageState({ path: identity.storageState });
}

setup("register the member account", async ({ request }) => {
  const response = await request.post("/api/v1/users/", { data: MEMBER_REGISTRATION });

  // 201 on a fresh database; a duplicate rejection on every run after that, which is the same end
  // state. Only a server fault is worth stopping for — signing in below is what proves the account.
  expect(response.status(), await response.text()).toBeLessThan(500);
});

setup("bank a superuser session", async ({ page }) => {
  await signInAndBankSession(page, SUPERUSER);
});

setup("bank a member session", async ({ page }) => {
  await signInAndBankSession(page, MEMBER);
});
