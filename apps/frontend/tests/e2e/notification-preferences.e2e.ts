import { expect, test } from "@playwright/test";
import { MEMBER } from "./identities";

test.use({ storageState: MEMBER.storageState });

// ACT-06 c1: I choose the channel per event type in my settings, and it sticks.
test("sets the channel for assigned tasks on the profile", async ({ page }) => {
  await page.goto("/profile");
  const card = page.getByRole("heading", { name: "Notifications" });
  await expect(card).toBeVisible();
  const channel = page.getByRole("combobox", { name: "Channel Task assigned to me" });
  await channel.click();
  await page.getByRole("option", { name: "By email only" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Notification preference saved." })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("combobox", { name: "Channel Task assigned to me" })).toHaveText("By email only");
  const saved: { kind: string; channel: string }[] = await (await page.request.get("/api/v1/notifications/preferences")).json();
  expect(saved.find((item) => item.kind === "task.assigned")?.channel).toBe("email");

  await page.getByRole("combobox", { name: "Channel Task assigned to me" }).click();
  await page.getByRole("option", { name: "In the app and by email" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Notification preference saved." })).toBeVisible();
});
