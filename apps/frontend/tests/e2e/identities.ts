import type { Page } from "@playwright/test";
import { PAGE_AUDIENCE, type PageAudience } from "@/lib/page-audience";

// Playwright resolves a relative storageState against the working directory, which both runners
// leave at apps/frontend. These are session cookies, so this path and the .gitignore entry
// covering it have to move together. `import.meta` is not an option here: Playwright transpiles
// this directory to CommonJS, because the package has no `"type": "module"`.
const bankedSessions = "tests/e2e/.auth";

export type Identity = {
  username: string;
  password: string;
  storageState: string;
};

/**
 * Defaults mirror `ADMIN_*` in apps/backend/.env.example, which is what
 * `scripts/setup_initial_data.py` seeds. A fork that changed them sets these two variables in the
 * environment it runs the suite from.
 */
export const SUPERUSER: Identity = {
  username: process.env.E2E_SUPERUSER_USERNAME ?? "admin",
  password: process.env.E2E_SUPERUSER_PASSWORD ?? "admin123",
  storageState: `${bankedSessions}/superuser.json`,
};

/** Registered by accounts.setup.ts through the public endpoint, so it holds `DEFAULT_ROLE_NAME`. */
export const MEMBER: Identity = {
  username: "e2emember",
  password: "E2eMember!1",
  storageState: `${bankedSessions}/member.json`,
};

export const MEMBER_REGISTRATION = {
  name: "E2E Member",
  username: MEMBER.username,
  email: "e2e.member@example.com",
  password: MEMBER.password,
};

/** Every path the manifest gives one audience kind, so a fork's own pages are what get exercised. */
export function pathsFor(kind: PageAudience["kind"]): string[] {
  return Object.entries(PAGE_AUDIENCE)
    .filter(([, audience]) => audience.kind === kind)
    .map(([path]) => path);
}

export async function submitCredentials(
  page: Page,
  credentials: { username: string; password: string },
) {
  await page.getByLabel("Username or email").fill(credentials.username);
  await page.getByLabel("Password").fill(credentials.password);
  await page.getByRole("button", { name: "Sign in securely" }).click();
}
