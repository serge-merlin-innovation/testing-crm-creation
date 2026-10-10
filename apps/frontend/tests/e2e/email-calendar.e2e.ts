import { expect, request as playwrightRequest, test } from "@playwright/test";
import { MEMBER, signInApi, runId } from "./identities";

const RUN = runId();
const INBOUND_SECRET = "e2e-inbound-secret";

/** The mail provider's webhook: no session, only the shared secret. */
async function deliver(baseURL: string, email: Record<string, unknown>) {
  const provider = await playwrightRequest.newContext({ baseURL });
  const response = await provider.post("/api/v1/email-logging/inbound", {
    headers: { "X-Inbound-Secret": INBOUND_SECRET },
    data: { spf: "pass", dkim: "pass", ...email },
  });
  const status = response.status();
  const body = await response.text();
  await provider.dispose();
  return { status, body };
}

test.describe("a user logging email and subscribing to the calendar", () => {
  test.use({ storageState: MEMBER.storageState });

  // ACT-04 c1/c2/c3 and CON-02 c2, through the UI.
  test("logs a BCC'd email on the contact and triages an unmatched one", async ({ page, baseURL }) => {
    const contactEmail = `jan.${RUN}@acme.example`;
    const headers = await signInApi(page.request, MEMBER);
    const contact = await page.request.post("/api/v1/contacts/", {
      headers,
      data: { first_name: "Jan", last_name: `Mail${RUN}`, email: contactEmail, source: "E2E" },
    });
    expect(contact.status(), await contact.text()).toBe(201);

    await page.goto("/profile");
    const address = page.getByLabel("Your CRM logging address");
    await expect(address).toHaveValue(/@/);
    const loggingAddress = await address.inputValue();

    const logged = await deliver(baseURL!, {
      sender: MEMBER.email,
      to: [contactEmail],
      bcc: [loggingAddress],
      subject: `Intro ${RUN}`,
      text: "Nice to meet you",
    });
    expect(logged.status, logged.body).toBe(202);
    expect(JSON.parse(logged.body).status).toBe("logged");

    const spoofed = await deliver(baseURL!, { sender: "spoof@evil.example", to: [contactEmail], bcc: [loggingAddress] });
    expect(spoofed.status).toBe(403);

    const unmatched = await deliver(baseURL!, {
      sender: MEMBER.email,
      to: [`nobody.${RUN}@nowhere.example`],
      bcc: [loggingAddress],
      subject: `Stray ${RUN}`,
    });
    expect(JSON.parse(unmatched.body).status).toBe("unmatched");

    await page.goto("/contacts");
    await page.getByRole("textbox", { name: "Search" }).fill(`Mail${RUN}`);
    await page.getByRole("button", { name: "Search" }).click();
    await page
      .getByRole("row")
      .filter({ hasText: `Mail${RUN}` })
      .getByRole("button", { name: "Who knows" })
      .click();
    const panel = page.getByRole("table", { name: `Who in the firm knows Jan Mail${RUN}` });
    await expect(panel.getByRole("row")).toHaveCount(2);
    await expect(panel.getByRole("row").nth(1).getByRole("cell").nth(1)).toHaveText("1");

    await page.goto("/inbox");
    const row = page.getByRole("row").filter({ hasText: `Stray ${RUN}` });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Discard" }).click();
    await expect(page.getByRole("status")).toHaveText("Email discarded.");
    await expect(page.getByRole("row").filter({ hasText: `Stray ${RUN}` })).toHaveCount(0);
  });

  // ACT-05 c1/c3.
  test("copies a working iCal URL and regenerating it kills the old one", async ({ page, baseURL }) => {
    await page.goto("/profile");
    const field = page.getByLabel("Your private calendar URL");
    await expect(field).toHaveValue(/\.ics$/);
    const oldUrl = await field.inputValue();

    const calendar = await playwrightRequest.newContext();
    const feed = await calendar.get(oldUrl);
    expect(feed.status()).toBe(200);
    expect(feed.headers()["content-type"]).toContain("text/calendar");
    expect(await feed.text()).toContain("BEGIN:VCALENDAR");

    await page.getByRole("button", { name: "Regenerate URL" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Regenerate" }).click();
    await expect(page.getByRole("status")).toHaveText("New URL ready. The old one no longer works.");
    await expect(field).not.toHaveValue(oldUrl);
    const newUrl = await field.inputValue();
    expect(newUrl.startsWith(baseURL!)).toBe(true);

    expect((await calendar.get(oldUrl)).status()).toBe(404);
    expect((await calendar.get(newUrl)).status()).toBe(200);
    await calendar.dispose();
  });
});
