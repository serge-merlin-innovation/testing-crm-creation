import { expect, test } from "@playwright/test";
import { MEMBER } from "./identities";

test.use({ storageState: MEMBER.storageState });

// AUTH-12 c1: from my own profile I set a travelling date range, and it shows as set after a reload.
test("a user flags their own travel dates on the profile", async ({ page }) => {
  await page.goto("/profile");
  const card = page.getByRole("region", { name: "Travelling (no new-country alerts)" });
  await card.getByLabel("From").fill("2031-03-01");
  await card.getByLabel("Until").fill("2031-03-15");
  await card.getByRole("button", { name: "Save travel dates" }).click();
  await expect(card.getByText("Travel dates saved.")).toBeVisible();

  await page.reload();
  await expect(card.getByLabel("From")).toHaveValue("2031-03-01");
  await expect(card.getByLabel("Until")).toHaveValue("2031-03-15");

  await card.getByRole("button", { name: "Clear" }).click();
  await expect(card.getByText("Travel dates saved.")).toBeVisible();
  await page.reload();
  await expect(card.getByLabel("From")).toHaveValue("");
});
