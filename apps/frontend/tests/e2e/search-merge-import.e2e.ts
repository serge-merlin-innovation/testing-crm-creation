import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";
import { ADMIN, MEMBER, signInApi } from "./identities";

const RUN = Date.now().toString(36);
const SURNAME = `Lefèvre${RUN}`;

/** An .xlsx built by the backend's own openpyxl, so the e2e needs no spreadsheet dependency. */
function workbook(rows: (string | null)[][]): Buffer {
  const script =
    "import json,sys,io;from openpyxl import Workbook;b=Workbook();s=b.active\n" +
    "for r in json.loads(sys.argv[1]): s.append(r)\n" +
    "o=io.BytesIO();b.save(o);sys.stdout.buffer.write(o.getvalue())";
  return execFileSync("uv", ["run", "--quiet", "python", "-c", script, JSON.stringify(rows)], { cwd: "../backend" });
}

test.describe("an analyst", () => {
  test.use({ storageState: MEMBER.storageState });

  // CON-03 c3 + c4 + CON-02 c1: create from an empty search, find it again with a typo and no
  // accent, and add myself as relationship holder.
  test("creates a contact from search, finds it fuzzily and claims the relationship", async ({ page }) => {
    await page.goto("/search");
    await page.getByLabel("Search", { exact: true }).fill(`Hélène ${SURNAME}`);
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByText("No results.")).toBeVisible();
    await page.getByRole("button", { name: "Create contact" }).click();
    await expect(page.getByRole("status")).toHaveText("Contact created.");

    await page.getByLabel("Search", { exact: true }).fill(`lefebvre${RUN}`);
    await page.getByRole("button", { name: "Search", exact: true }).click();
    const contacts = page.getByRole("list", { name: "Contacts" });
    await expect(contacts).toContainText(`Hélène ${SURNAME}`);

    await page.getByLabel(`How well I know them ${SURNAME}`).click();
    await page.getByRole("option", { name: "3 - close" }).click();
    await contacts.getByRole("button", { name: "Add me as relationship holder" }).first().click();
    await expect(page.getByRole("status")).toHaveText("Relationship saved.");
    await expect(contacts).toContainText("Known by: Eva Analyst (3/3)");

    await page.goto("/contacts");
    await expect(page.getByRole("row").filter({ hasText: SURNAME })).toContainText("Eva Analyst (3/3)");
  });

  // CON-03 c2: save a filter, share it, and reuse it.
  test("saves, shares and reuses a filter", async ({ page }) => {
    await page.goto("/search");
    await page.getByLabel("Company type").click();
    await page.getByRole("option", { name: "financial_investor" }).click();
    await page.getByLabel("Filter name").fill(`PE funds ${RUN}`);
    await page.getByLabel("Share").check();
    await page.getByRole("button", { name: "Save filter" }).click();
    await expect(page.getByRole("status")).toHaveText("Filter saved.");

    await page.goto("/search");
    const saved = page.getByRole("listitem").filter({ hasText: `PE funds ${RUN}` });
    await expect(saved).toContainText("Shared");
    await saved.getByRole("button", { name: `Apply PE funds ${RUN}` }).click();
    await expect(page.getByRole("list", { name: "Companies" }).or(page.getByText("No results."))).toBeVisible();
  });

  // CON-03 c1: results are grouped by type.
  test("sees results grouped by type", async ({ page, request }) => {
    const headers = await signInApi(request, MEMBER);
    const countries: { id: number; code: string }[] = await (await request.get("/api/v1/picklists/?kind=country")).json();
    const company = await request.post("/api/v1/companies/", {
      headers,
      data: {
        name: `Zephyr ${RUN} Holding`,
        type: "target",
        country_id: countries.find((country) => country.code === "NL")!.id,
        vat_or_registry_number: `ZP-${RUN}`,
        ignore_similar: true,
      },
    });
    expect(company.status(), await company.text()).toBe(201);
    await request.post("/api/v1/contacts/", {
      headers,
      data: { first_name: "Zoe", last_name: `Zephyr${RUN}`, source: "E2E", company_id: (await company.json()).id },
    });

    await page.goto("/search");
    await page.getByLabel("Search", { exact: true }).fill(`zephyr${RUN}`);
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Companies" })).toBeVisible();
    await expect(page.getByRole("list", { name: "Companies" })).toContainText(`Zephyr ${RUN} Holding`);
    await expect(page.getByRole("list", { name: "Contacts" })).toContainText(`Zoe Zephyr${RUN}`);
    await expect(page.getByRole("heading", { name: "Deals" })).toBeVisible();
  });

  // CON-04 c1: merge two duplicates, picking a field value.
  test("merges two duplicate contacts", async ({ page, request }) => {
    const headers = await signInApi(request, MEMBER);
    const ids: number[] = [];
    for (const email of [`old.${RUN}@example.com`, `new.${RUN}@example.com`]) {
      const created = await request.post("/api/v1/contacts/", {
        headers,
        data: { first_name: "Dup", last_name: `Twin${RUN}`, email, source: "E2E" },
      });
      ids.push((await created.json()).id);
    }

    await page.goto("/merge");
    await page.getByLabel("Keep record (id)").fill(String(ids[0]));
    await page.getByLabel("Duplicate (id)").fill(String(ids[1]));
    await page.getByRole("button", { name: "Compare" }).click();
    await page.getByLabel("Keep email").click();
    await page.getByRole("option", { name: `new.${RUN}@example.com` }).click();
    await page.getByRole("button", { name: "Merge", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText("Merged. History moved to the kept record.");

    const kept = await (await request.get(`/api/v1/contacts/${ids[0]}`)).json();
    expect(kept.email).toBe(`new.${RUN}@example.com`);
    expect((await request.get(`/api/v1/contacts/${ids[1]}`)).status()).toBe(404);
  });

  test("is not offered the import page", async ({ page }) => {
    await page.goto("/overview");
    await expect(page.getByRole("link", { name: "Import" })).toHaveCount(0);
  });
});

test.describe("an admin", () => {
  test.use({ storageState: ADMIN.storageState });

  // CON-05 c1 + c2: map columns, preview new/duplicate/error rows, confirm, download the errors.
  test("imports contacts from Excel with a preview and an error file", async ({ page }) => {
    const file = workbook([
      ["Voornaam", "Achternaam", "E-mail"],
      ["Els", `Maes${RUN}`, `els.${RUN}@example.com`],
      ["Els", `Maes${RUN}`, `els.${RUN}@example.com`],
      ["Piet", null, `piet.${RUN}@example.com`],
    ]);

    await page.goto("/imports");
    await page.getByLabel("Excel file (.xlsx)").setInputFiles({
      name: "legacy.xlsx",
      mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: file,
    });
    await page.getByRole("button", { name: "Upload" }).click();
    for (const [field, column] of [
      ["first_name", "Voornaam"],
      ["last_name", "Achternaam"],
      ["email", "E-mail"],
    ]) {
      await page.getByLabel(`Column in file ${field}`).click();
      await page.getByRole("option", { name: column }).click();
    }
    await page.getByRole("button", { name: "Preview" }).click();
    await expect(page.getByText("New: 1")).toBeVisible();
    await expect(page.getByText("Duplicates: 1")).toBeVisible();
    await expect(page.getByText("Errors: 1")).toBeVisible();
    await expect(page.getByRole("row").filter({ hasText: "last_name is required" })).toContainText("4");

    await page.getByRole("button", { name: "Confirm import" }).click();
    await expect(page.getByRole("status")).toHaveText("Import completed. Created: 1");
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download error file" }).click();
    expect((await download).suggestedFilename()).toMatch(/^import-\d+-errors\.xlsx$/);
  });

  // CON-04 c2: an admin undoes a recent merge.
  test("undoes a recent merge", async ({ page }) => {
    await page.goto("/merge");
    const undo = page.getByRole("button", { name: "Undo" }).first();
    await expect(undo).toBeVisible();
    await undo.click();
    await expect(page.getByRole("status")).toHaveText("Merge undone.");
  });
});
