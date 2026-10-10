import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { currentCode, saveSecret } from "./totp";

// Playwright resolves a relative storageState against the working directory, which both runners
// leave at apps/frontend. These are session cookies, so this path and the .gitignore entry
// covering it have to move together. `import.meta` is not an option here: Playwright transpiles
// this directory to CommonJS, because the package has no `"type": "module"`.
const bankedSessions = "tests/e2e/.auth";

export type Identity = {
  email: string;
  password: string;
  storageState: string;
};

/**
 * Defaults mirror `FIRST_ADMIN_*` in apps/backend/.env.example, which is what
 * `scripts/setup_initial_data.py` seeds. A fork that changed them sets these two variables in the
 * environment it runs the suite from.
 */
export const ADMIN: Identity = {
  email: process.env.E2E_ADMIN_EMAIL ?? "admin@example.com",
  password: process.env.E2E_ADMIN_PASSWORD ?? "admin123",
  storageState: `${bankedSessions}/admin.json`,
};

/** Created by accounts.setup.ts through the admin API and given the Analyst / Associate role. */
export const MEMBER: Identity = {
  email: "e2e.member@example.com",
  password: "E2eMember!1",
  storageState: `${bankedSessions}/member.json`,
};

export const MEMBER_ROLE = "Analyst / Associate";

export async function submitCredentials(
  page: Page,
  credentials: { email: string; password: string },
) {
  await page.getByLabel("Email").fill(credentials.email);
  await page.getByLabel("Password").fill(credentials.password);
  await page.getByRole("button", { name: "Sign in securely" }).click();
}

/** Password, then enrolment (first time) or the authenticator code: the whole sign-in. */
export async function signIn(page: Page, identity: { email: string; password: string }) {
  await submitCredentials(page, identity);

  const enrol = page.getByRole("heading", { name: "Set up two-factor sign-in" });
  const code = page.getByRole("heading", { name: "Authentication code" });
  await expect(enrol.or(code)).toBeVisible();

  if (await enrol.isVisible()) {
    saveSecret(identity.email, await page.getByLabel("Or enter this key by hand").inputValue());
  }

  await page.getByLabel("Code", { exact: true }).fill(currentCode(identity.email));
  await page.getByRole("button", { name: "Verify" }).click();

  const recovery = page.getByRole("heading", { name: "Your recovery codes" });
  const left = page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await Promise.race([recovery.waitFor(), left]);
  if (await recovery.isVisible()) {
    await expect(page.getByRole("list", { name: "Your recovery codes" }).getByRole("listitem")).toHaveCount(10);
    await page.getByRole("button", { name: "Continue" }).click();
  }
}

/** The same whole sign-in over the API: password, then enrolment or the code. Returns CSRF headers. */
export async function signInApi(request: APIRequestContext, identity: { email: string; password: string }) {
  const login = await request.post("/api/v1/auth/login", { form: identity });
  expect(login.status(), await login.text()).toBe(200);
  const first = await login.json();
  if (first.step === "done") return { "X-CSRF-Token": first.csrf_token as string };

  if (first.step === "enrol") {
    saveSecret(identity.email, new URL(first.otpauth_uri).searchParams.get("secret")!);
  }
  const verified = await request.post("/api/v1/auth/login/second-factor", {
    data: { challenge: first.challenge, code: currentCode(identity.email) },
  });
  expect(verified.status(), await verified.text()).toBe(200);
  return { "X-CSRF-Token": (await verified.json()).csrf_token as string };
}
