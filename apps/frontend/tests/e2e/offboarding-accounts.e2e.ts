import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import { ADMIN, inviteUser, signIn, signInApi, type Invitee } from "./identities";
import { currentCode, saveSecret } from "./totp";

const RUN = Date.now().toString(36);

function invitee(name: string): Invitee {
  return {
    firstName: name,
    lastName: `Run${RUN}`,
    email: `e2e.${name.toLowerCase()}.${RUN}@example.com`,
    password: "Amber-Lighthouse-91-Quill",
  };
}

async function emailedLink(request: APIRequestContext, to: string, path: string): Promise<string> {
  const emails: { body: string }[] = await (await request.get("/api/v1/test-hooks/emails", { params: { to } })).json();
  const link = emails
    .map((email) => email.body.match(new RegExp(`(/${path}\\?token=[\\w-]+)`))?.[1])
    .findLast((match) => match !== undefined);
  expect(link, `${path} link emailed to ${to}`).toBeTruthy();
  return link!;
}

async function roleId(request: APIRequestContext, name: string): Promise<number> {
  const roles: { id: number; name: string }[] = await (await request.get("/api/v1/roles/")).json();
  return roles.find((role) => role.name === name)!.id;
}

async function finishEnrolment(page: Page, email: string) {
  await expect(page.getByRole("heading", { name: "Set up two-factor sign-in" })).toBeVisible();
  saveSecret(email, await page.getByLabel("Or enter this key by hand").inputValue());
  await page.getByLabel("Code", { exact: true }).fill(currentCode(email));
  await page.getByRole("button", { name: "Verify" }).click();
  await expect(page.getByRole("heading", { name: "Your recovery codes" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();
}

// AUTH-08 (#4 frontend): the emailed invitation link sets the password and enrols 2FA in the browser.
test("an invitee sets a password and enrols from the invitation page", async ({ browser, page }) => {
  const person = invitee("Ines");
  const adminContext = await browser.newContext();
  const admin = adminContext.request;
  const headers = await signInApi(admin, ADMIN);
  await admin.post("/api/v1/test-hooks/emails/capture");
  const created = await admin.post("/api/v1/users/", {
    headers,
    data: {
      first_name: person.firstName,
      last_name: person.lastName,
      email: person.email,
      role_id: await roleId(admin, "Analyst / Associate"),
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const link = await emailedLink(admin, person.email, "accept-invitation");
  await adminContext.close();

  await page.goto(link);
  await expect(page.getByLabel("Email")).toHaveValue(person.email);
  await page.getByLabel("New password", { exact: true }).fill(person.password);
  await page.getByLabel("Repeat the password").fill("something-else-entirely");
  await page.getByRole("button", { name: "Set my password" }).click();
  await expect(page.getByText("The two passwords differ.")).toBeVisible();

  await page.getByLabel("Repeat the password").fill(person.password);
  await page.getByRole("button", { name: "Set my password" }).click();
  await finishEnrolment(page, person.email);

  await expect(page).toHaveURL("/overview");
  await page.goto(link);
  await expect(page.getByText("expired or was already used")).toBeVisible();
});

// AUTH-10 (#4 frontend): forgot password from the login page, then the emailed reset link.
test("a user resets a forgotten password through the emailed link", async ({ browser, page }) => {
  const person = invitee("Remi");
  const adminContext = await browser.newContext();
  const headers = await signInApi(adminContext.request, ADMIN);
  await inviteUser(browser, adminContext.request, headers, person, "Analyst / Associate");

  await page.goto("/login");
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await expect(page).toHaveURL("/reset-password");
  await page.getByLabel("Email").fill(person.email);
  await page.getByRole("button", { name: "Send the link" }).click();
  await expect(page.getByRole("status")).toContainText("If an account exists");

  const link = await emailedLink(adminContext.request, person.email, "reset-password");
  await adminContext.close();
  await page.goto(link);
  const newPassword = "Granite-Orchard-58-Comet";
  await page.getByLabel("New password", { exact: true }).fill(newPassword);
  await page.getByLabel("Repeat the password").fill(newPassword);
  await page.getByRole("button", { name: "Set my password" }).click();
  await expect(page.getByRole("status")).toContainText("Your password was changed");

  await page.getByRole("link", { name: "Back to sign in" }).click();
  await signIn(page, { email: person.email, password: newPassword });
  await expect(page).toHaveURL("/overview");
});

const LEAVER = invitee("Lea");
const TRAVELLER = invitee("Theo");

// Seeded outside the admin-session describe: its storageState would ride along on every new context.
test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext();
  const headers = await signInApi(context.request, ADMIN);
  await inviteUser(browser, context.request, headers, LEAVER, "Analyst / Associate");
  await inviteUser(browser, context.request, headers, TRAVELLER, "Analyst / Associate");
  await context.close();
});

async function adminPage(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ storageState: ADMIN.storageState });
  return context.newPage();
}

test.describe("admin user screens", () => {

  // ADM-03 + AUTH-05 c4: hand over records, see the confirmation, and the leaver's session is refused.
  test("an admin offboards a leaver with hand-over, then reactivates them", async ({ browser }) => {
    const page = await adminPage(browser);
    const person = LEAVER;
    const leaver = await browser.newContext();
    const leaverHeaders = await signInApi(leaver.request, person);
    const contact = await leaver.request.post("/api/v1/contacts/", {
      headers: leaverHeaders,
      data: { first_name: "Hannah", last_name: `Owned${RUN}`, source: "E2E" },
    });
    expect(contact.status(), await contact.text()).toBe(201);

    await page.goto("/users");
    await page.getByRole("button", { name: `Manage ${person.email}` }).click();
    await expect(page.getByRole("list", { name: "Records to hand over" })).toContainText(`Hannah Owned${RUN}`);
    const deactivate = page.getByRole("button", { name: "Deactivate", exact: true });
    await expect(deactivate).toBeDisabled();

    await page.getByLabel("New owner").click();
    await page.getByRole("option").first().click();
    await deactivate.click();
    await page.getByRole("button", { name: "Deactivate now" }).click();

    const confirmation = page.getByRole("definition");
    await expect(page.getByRole("heading", { name: "Offboarding done" })).toBeVisible();
    await expect(confirmation.first()).toHaveText(/[1-9]/);
    await expect(page.getByRole("list", { name: "Records to hand over" })).toContainText(`contact: Hannah Owned${RUN}`);
    expect((await leaver.request.get("/api/v1/users/me")).status()).toBe(401);
    await leaver.close();

    await page.getByRole("tab", { name: "Deactivated" }).click();
    await page.getByRole("button", { name: `Manage ${person.email}` }).click();
    await page.getByRole("button", { name: "Reactivate" }).click();
    await expect(page.getByRole("status")).toContainText("Reactivated with their role");
  });

  // #2 admin screens: unlock, 2FA reset, travel flag and the trusted-device policy.
  test("an admin resets 2FA, flags travel and toggles trusted devices", async ({ browser }) => {
    const page = await adminPage(browser);
    const person = TRAVELLER;

    await page.goto("/users");
    await page.getByRole("button", { name: `Manage ${person.email}` }).click();
    await expect(page.getByText("Not locked")).toBeVisible();
    await expect(page.getByRole("button", { name: "Unlock" })).toBeDisabled();

    await page.getByLabel("From").fill("2026-11-01");
    await page.getByLabel("Until").fill("2026-11-10");
    await page.getByRole("button", { name: "Save travel dates" }).click();
    await expect(page.getByRole("status")).toContainText("Travel dates saved.");

    await page.getByRole("button", { name: "Reset two-factor" }).click();
    await expect(page.getByRole("status")).toContainText("Two-factor was reset");
    await expect(page.getByText("Not set up")).toBeVisible();

    const trusted = page.getByRole("switch", { name: 'Allow "Trust this device for 30 days"' });
    const before = await trusted.getAttribute("aria-checked");
    await trusted.click();
    await expect(trusted).not.toHaveAttribute("aria-checked", before!);
    await trusted.click();
    await expect(trusted).toHaveAttribute("aria-checked", before!);
  });
});
