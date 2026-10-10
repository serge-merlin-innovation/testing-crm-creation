import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { formatAmount, formatDate, formatDateTime, formatIsoDate, formatNumber } from "@/lib/i18n/format";
import { MESSAGES, resolveLanguage, translate } from "@/lib/i18n/messages";

describe("message catalogues", () => {
  it("carry the same keys in EN, FR and NL", () => {
    const keys = Object.values(MESSAGES).map((catalogue) => Object.keys(catalogue).sort());

    expect(keys[1]).toEqual(keys[0]);
    expect(keys[2]).toEqual(keys[0]);
  });

  it("translates into the chosen language and falls back to English", () => {
    expect(translate("fr", "login.title")).toBe("Connexion");
    expect(translate("nl", "login.title")).toBe("Aanmelden");
    expect(resolveLanguage("de")).toBe("en");
  });
});

describe("Belgian formats", () => {
  it.each(["en", "fr", "nl"] as const)("writes dates DD/MM/YYYY in %s", (language) => {
    expect(formatDate(new Date(Date.UTC(2026, 2, 7, 10)), language)).toBe("07/03/2026");
  });

  it.each([
    ["fr", "1.234,56"],
    ["nl", "1.234,56"],
    ["en", "1,234.56"],
  ] as const)("writes numbers in %s as %s", (language, expected) => {
    expect(formatNumber(1234.56, language)).toBe(expected);
  });
});

describe("Belgian formats for every kind of value (NFR-04 c4)", () => {
  it("writes an ISO calendar date as DD/MM/YYYY without shifting the day", () => {
    expect(formatIsoDate("2026-03-07", "fr")).toBe("07/03/2026");
    expect(formatIsoDate("2026-12-31T23:30:00Z", "nl")).toBe("01/01/2027");
    expect(formatIsoDate(null, "en")).toBe("");
  });

  it("writes date and time in Brussels time", () => {
    expect(formatDateTime("2026-07-01T06:05:00Z", "nl")).toBe("01/07/2026 08:05");
  });

  it.each([
    ["fr", "25.000"],
    ["nl", "25.000"],
    ["en", "25,000"],
  ] as const)("writes amounts in %s without decimals as %s", (language, expected) => {
    expect(formatAmount("25000", language)).toBe(expected);
    expect(formatAmount(null, language)).toBe("");
  });
});

describe("no page formats a date or number by itself", () => {
  const files = readdirSync(join(__dirname, "../../../src"), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && /\.tsx?$/.test(entry.name))
    .map((entry) => join(entry.parentPath, entry.name))
    .filter((path) => !path.includes("lib/i18n/format.ts") && !path.includes("components/ui/"));

  it.each(files)("%s uses lib/i18n/format", (path) => {
    const source = readFileSync(path, "utf8");
    expect(source).not.toMatch(/toLocale(Date|Time)?String\(/);
    expect(source).not.toMatch(/new Intl\.(NumberFormat|DateTimeFormat)/);
    // A raw ISO date or amount field rendered straight into JSX.
    expect(source).not.toMatch(
      /[>\s]\{(?!errors\.)[\w.]+\.(due_date|planned_date|actual_date|sent_date|signed_date|closing_date|revisit_date|estimated_ev|final_ev|expected_fee|amount|ev)\}/,
    );
  });
});
