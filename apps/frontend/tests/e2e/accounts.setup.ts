import { expect, test as setup, type Page } from "@playwright/test";
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH } from "@/lib/auth-routing";
import { ADMIN, MEMBER, MEMBER_ROLE, inviteUser, signIn, signInApi, type Identity } from "./identities";

async function signInAndBankSession(page: Page, identity: Identity) {
  await page.goto(LOGIN_PATH);
  await signIn(page, identity);

  await expect(
    page,
    `${identity.email} could not sign in. If this fork changed the seeded admin, set ` +
      `E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD.`,
  ).toHaveURL(DEFAULT_AUTHENTICATED_PATH);

  await page.context().storageState({ path: identity.storageState });
}

setup("bank an admin session", async ({ page }) => {
  await signInAndBankSession(page, ADMIN);
});

setup("invite the member account with the Analyst role", async ({ browser, request }) => {
  const headers = await signInApi(request, ADMIN);
  await inviteUser(browser, request, headers, MEMBER, MEMBER_ROLE);
});

setup("bank a member session", async ({ page }) => {
  await signInAndBankSession(page, MEMBER);
});
