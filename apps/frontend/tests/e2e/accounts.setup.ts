import { expect, test as setup, type Page } from "@playwright/test";
import { DEFAULT_AUTHENTICATED_PATH, LOGIN_PATH } from "@/lib/auth-routing";
import { currentCode } from "./totp";
import { ADMIN, MEMBER, MEMBER_ROLE, signIn, type Identity } from "./identities";

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

setup("create the member account with the Analyst role", async ({ request }) => {
  const login = await request.post("/api/v1/auth/login", {
    form: { email: ADMIN.email, password: ADMIN.password },
  });
  expect(login.status(), await login.text()).toBe(200);
  const verified = await request.post("/api/v1/auth/login/second-factor", {
    data: { challenge: (await login.json()).challenge, code: currentCode(ADMIN.email) },
  });
  expect(verified.status(), await verified.text()).toBe(200);
  const headers = { "X-CSRF-Token": (await verified.json()).csrf_token };

  // 201 on a fresh database; 409 on every run after that, which is the same end state.
  const created = await request.post("/api/v1/users/", {
    headers,
    data: { name: "E2E Member", email: MEMBER.email, password: MEMBER.password },
  });
  expect(created.status(), await created.text()).toBeLessThan(500);

  const roles: { id: number; name: string }[] = await (await request.get("/api/v1/roles/")).json();
  const users: { data: { id: number; email: string }[] } = await (
    await request.get("/api/v1/users/", { params: { items_per_page: 100 } })
  ).json();
  const member = users.data.find((user) => user.email === MEMBER.email);
  const role = roles.find((candidate) => candidate.name === MEMBER_ROLE);
  expect(member && role).toBeTruthy();

  const assigned = await request.patch(`/api/v1/users/${member!.id}/role`, {
    headers,
    data: { role_id: role!.id },
  });
  expect(assigned.status(), await assigned.text()).toBe(200);
});

setup("bank a member session", async ({ page }) => {
  await signInAndBankSession(page, MEMBER);
});
