import { expect, test } from "@playwright/test";
import { ADMIN, runId } from "./identities";

const RUN = runId();

test.use({ storageState: ADMIN.storageState });

// ACT-01 c1, c3, c4: log on a record's timeline, edit later and see "Edited", delete, admin restores.
test("logs, edits with an edited marker, deletes and restores an activity on a company timeline", async ({ page }) => {
  const countries: { id: number; code: string }[] = await (await page.request.get("/api/v1/picklists/?kind=country")).json();
  await page.goto("/companies");
  await page.getByLabel("Name").fill(`Timeline Works ${RUN}`);
  await page.getByLabel("Country").click();
  await page.getByRole("option", { name: "Netherlands" }).click();
  await page.getByLabel("VAT or registry number").fill(`TL-${RUN}`);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("Company created.");
  expect(countries.length).toBeGreaterThan(0);

  await page.getByRole("textbox", { name: "Search" }).fill(`Timeline Works ${RUN}`);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("row", { name: new RegExp(`Timeline Works ${RUN}`) }).getByRole("button", { name: "Timeline" }).click();
  const panel = page.getByRole("region", { name: `Timeline Timeline Works ${RUN}` });

  await panel.getByLabel("Activity note").fill(`Intro call ${RUN}`);
  await panel.getByRole("button", { name: "Log activity" }).click();
  await expect(panel.getByRole("status")).toHaveText("Activity logged.");
  const activities = panel.getByRole("region", { name: "Activities", exact: true });
  await expect(activities).toContainText(`Intro call ${RUN}`);

  await panel.getByLabel("Note", { exact: true }).fill(`Shared note ${RUN}`);
  await panel.getByRole("button", { name: "Add note" }).click();
  await expect(panel.getByRole("region", { name: "Notes", exact: true })).toContainText(`Shared note ${RUN}`);

  const later = new Date(Date.now() + 8 * 24 * 3600 * 1000).toISOString();
  const clock = await page.request.put("/api/v1/test-hooks/clock", { data: { now: later } });
  expect(clock.status(), await clock.text()).toBeLessThan(300);
  try {
    await activities.getByRole("button", { name: "Edit" }).click();
    const dialog = page.getByRole("dialog", { name: "Edit activity" });
    await dialog.getByLabel("Activity note").fill(`Intro call revised ${RUN}`);
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(panel.getByRole("status")).toHaveText("Activity updated.");
    await expect(activities).toContainText(`Intro call revised ${RUN}`);
    await expect(activities.getByText(/^Edited /)).toBeVisible();
  } finally {
    await page.request.put("/api/v1/test-hooks/clock", { data: { now: null } });
  }

  await activities.getByRole("button", { name: "Delete" }).click();
  await expect(panel.getByRole("status")).toHaveText("Activity deleted.");
  await expect(activities).not.toContainText(`Intro call revised ${RUN}`);

  await panel.getByRole("region", { name: "Deleted activities" }).getByRole("button", { name: "Restore" }).first().click();
  await expect(panel.getByRole("status")).toHaveText("Activity restored.");
  await expect(activities).toContainText(`Intro call revised ${RUN}`);
});
