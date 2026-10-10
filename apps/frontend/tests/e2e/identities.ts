import type { Page } from "@playwright/test";

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
