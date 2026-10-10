import { describe, expect, it } from "vitest";
import { formatDate, formatNumber } from "@/lib/i18n/format";
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
