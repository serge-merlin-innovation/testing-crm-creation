import { expect, test } from "@playwright/test";
import { MEMBER, runId, signInApi } from "./identities";

const RUN = runId();

test.use({ storageState: MEMBER.storageState });

// ACT-03 c1: a task assigned to me appears in My tasks, and I complete it there.
test("lists my tasks and completes one", async ({ browser, page }) => {
  const api = await browser.newContext();
  const headers = await signInApi(api.request, MEMBER);
  const me: { id: number } = await (await api.request.get("/api/v1/users/me")).json();
  const title = `Send teaser ${RUN}`;
  const task = await api.request.post("/api/v1/tasks/", {
    headers,
    data: { title, assignee_id: me.id, due_date: new Date().toISOString().slice(0, 10) },
  });
  expect(task.status(), await task.text()).toBe(201);
  await api.close();

  await page.goto("/");
  await page.getByRole("link", { name: "My tasks" }).click();
  await expect(page.getByRole("heading", { name: "My tasks", level: 1 })).toBeVisible();
  await expect(page.getByRole("cell", { name: title, exact: true })).toBeVisible();
  await page.getByRole("button", { name: `Complete ${title}` }).click();
  await expect(page.getByRole("status")).toHaveText("Task completed.");
  await expect(page.getByRole("cell", { name: title, exact: true })).toHaveCount(0);

  await page.getByLabel("Show").click();
  await page.getByRole("option", { name: "All tasks, done included" }).click();
  await expect(page.getByRole("row", { name: new RegExp(title) })).toContainText("Done");
});
