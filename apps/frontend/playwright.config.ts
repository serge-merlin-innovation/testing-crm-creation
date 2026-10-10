import {
  defineConfig,
  devices,
  type ReporterDescription,
} from "@playwright/test";

// Dedicated ports, and servers are never reused: on the default ports Playwright will happily
// adopt whatever already answers — a stale build, or another project's app entirely — and the
// suite then passes or fails against code nobody is looking at.
// Overridable so parallel worktrees can each run their own suite.
const FRONTEND_PORT = process.env.E2E_FRONTEND_PORT ?? "3100";
const BACKEND_PORT = process.env.E2E_BACKEND_PORT ?? "8100";
const FRONTEND_URL = `http://localhost:${FRONTEND_PORT}`;
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;

export default defineConfig({
  testDir: "./tests/e2e",
  // `.e2e.ts` is the second, independent guard against Vitest collecting these — see
  // vitest.config.ts, which owns the first.
  testMatch: /.*\.e2e\.ts$/,
  // One shared database and one shared login-lockout key: parallel workers race on both.
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ...(process.env.CI
      ? ([
          ["list"],
          ["html", { open: "never" }],
        ] satisfies ReporterDescription[])
      : [["list"] as const]),
    ["../../scripts/check-failures/playwright-reporter.mjs"],
  ],
  use: {
    baseURL: FRONTEND_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "on-first-retry",
  },
  projects: [
    // A setup *project*, not `globalSetup`: globalSetup runs before `webServer`, so it could not
    // reach the API it registers accounts against.
    { name: "accounts", testMatch: /accounts\.setup\.ts$/ },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["accounts"],
    },
  ],
  webServer: [
    {
      command: `uv run fastapi run src/interfaces/main.py --port ${BACKEND_PORT}`,
      cwd: "../backend",
      url: `${BACKEND_URL}/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        // Pinned, not inherited: a developer's .env and a fork's .env disagree, and a gate whose
        // configuration varies proves nothing. CSRF on is what exercises apiFetch's mint-and-retry.
        CSRF_ENABLED: "true",
        SESSION_SECURE_COOKIES: "false",
        // The feed URL is built from APP_URL; the inbound-mail webhook needs a secret to accept anything.
        APP_URL: FRONTEND_URL,
        INBOUND_EMAIL_SECRET: "e2e-inbound-secret",
        // Every spec's beforeAll opens its own admin API session; at the default cap of 5 the oldest
        // one evicted is the banked admin storage state that later specs browse with.
        MAX_SESSIONS_PER_USER: "50",
      },
    },
    {
      command: "pnpm start",
      url: FRONTEND_URL,
      timeout: 120_000,
      reuseExistingServer: false,
      env: { PORT: FRONTEND_PORT, BACKEND_URL },
    },
  ],
});
