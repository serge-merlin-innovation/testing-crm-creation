import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { MESSAGES } from "@/lib/i18n/messages";

// NFR-04 c1: every label comes from the EN/FR/NL catalogue. These are codes, not words.
const NOT_WORDS = new Set(["https://", "name@firm.be", "EN", "FR", "NL", "IM", "M&amp;A CRM"]);
// Terms of art the firm uses unchanged in Dutch.
const SAME_IN_DUTCH = new Set(["Wall crossing", "EV/EBITDA min", "EV/EBITDA max"]);
const TEXT_ATTRIBUTES = new Set(["placeholder", "aria-label", "title", "alt", "label"]);

const SOURCE = join(__dirname, "../../../src");
const pages = readdirSync(SOURCE, { recursive: true, withFileTypes: true })
  .filter((entry) => entry.isFile() && entry.name.endsWith(".tsx"))
  .map((entry) => join(entry.parentPath, entry.name))
  .filter((path) => !path.includes("components/ui/"));

function literalText(path: string): string[] {
  const file = ts.createSourceFile(path, readFileSync(path, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node) && /[A-Za-z]{2,}/.test(node.text.trim())) {
      found.push(node.text.trim());
    }
    if (
      ts.isJsxAttribute(node) &&
      TEXT_ATTRIBUTES.has(node.name.getText()) &&
      node.initializer &&
      ts.isStringLiteral(node.initializer) &&
      /[A-Za-z]{2,}/.test(node.initializer.text)
    ) {
      found.push(node.initializer.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return found.filter((text) => !NOT_WORDS.has(text));
}

describe("every label is translated (NFR-04 c1)", () => {
  it.each(pages)("%s has no hard-coded label", (path) => {
    expect(literalText(path)).toEqual([]);
  });

  it("FR and NL translate nearly every message, not copy the English", () => {
    const keys = Object.keys(MESSAGES.en) as (keyof typeof MESSAGES.en)[];
    for (const language of ["fr", "nl"] as const) {
      const copied = keys.filter(
        (key) =>
          MESSAGES[language][key] === MESSAGES.en[key] &&
          /[a-z]{4,} [a-z]{3,}/i.test(MESSAGES.en[key]) &&
          !(language === "nl" && SAME_IN_DUTCH.has(MESSAGES.en[key])),
      );
      // Shared single words (Code, Status, Contact, KYC) are legitimately identical; whole phrases are not.
      expect(copied, `${language} copies English phrases`).toEqual([]);
    }
  });
});
